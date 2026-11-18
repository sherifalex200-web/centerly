"""تطبيق الأوفلاين: صفحة التطبيق + تحميل البيانات + استقبال المزامنة.
لا يحتاج أي migration: التكرار يُمنع بالقيود الموجودة أصلاً
(Attendance: session+student، Payment: student+group+month)."""
import json
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.views.decorators.http import require_GET, require_POST

from .models import Attendance, Enrollment, Group, Payment, Session, Student, current_month


def api(view):
    @wraps(view)
    def wrapper(request, *a, **k):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'auth'}, status=401)
        if not getattr(request, 'center', None):
            return JsonResponse({'error': 'no center'}, status=403)
        return view(request, *a, **k)
    return wrapper


@login_required
def app_page(request):
    if not getattr(request, 'center', None):
        return HttpResponseForbidden('الحساب غير مرتبط بسنتر')
    return render(request, 'offline/app.html')


def service_worker(request):
    resp = render(request, 'offline/sw.js', content_type='application/javascript')
    resp['Cache-Control'] = 'no-cache'
    return resp


def manifest(request):
    return JsonResponse({
        'name': 'Centerly', 'short_name': 'Centerly', 'start_url': '/app/', 'scope': '/app/',
        'display': 'standalone', 'dir': 'rtl', 'lang': 'ar',
        'background_color': '#12332f', 'theme_color': '#12332f',
        'icons': [{'src': '/app/icon.svg', 'sizes': 'any', 'type': 'image/svg+xml', 'purpose': 'any'}],
    }, content_type='application/manifest+json')


def icon(request):
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
           '<rect width="512" height="512" rx="110" fill="#12332f"/>'
           '<path d="M150 270l70 70 150-170" fill="none" stroke="#f2b134" stroke-width="56" '
           'stroke-linecap="round" stroke-linejoin="round"/></svg>')
    return HttpResponse(svg, content_type='image/svg+xml')


@api
@require_GET
def bootstrap(request):
    c, today, m = request.center, timezone.localdate(), current_month()
    groups = Group.objects.for_center(c).filter(is_active=True).select_related('teacher')
    return JsonResponse({
        'center': c.name, 'today': today.isoformat(), 'month': m.isoformat(),
        'students': [{'id': s.id, 'n': s.name, 'b': s.barcode, 'p': s.parent_phone, 'ph': s.phone}
                     for s in Student.objects.for_center(c).filter(is_active=True)],
        'groups': [{'id': g.id, 'n': g.name, 't': g.teacher.name, 'st': g.start_time.strftime('%H:%M'),
                    'fee': float(g.monthly_fee), 'today': today.weekday() in g.days} for g in groups],
        'enr': list(Enrollment.objects.for_center(c).filter(is_active=True)
                    .values_list('student_id', 'group_id')),
        'paid': list(Payment.objects.for_center(c).filter(month=m).values_list('student_id', 'group_id')),
        'att': list(Attendance.objects.for_center(c).filter(session__date=today)
                    .values_list('session__group_id', 'student_id')),
    })


def _when(op):
    dt = parse_datetime(op.get('at') or '')
    if not dt:
        return timezone.now()
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


def _apply(request, op):
    c = request.center
    try:
        student = Student.objects.for_center(c).get(pk=op['student_id'])
        group = Group.objects.for_center(c).get(pk=op['group_id'])
    except (Student.DoesNotExist, Group.DoesNotExist, KeyError):
        raise ValueError('الطالب أو المجموعة غير موجودة')
    when = _when(op)

    if op.get('type') == 'attendance':
        day = parse_date(op.get('date') or '') or timezone.localtime(when).date()
        session, _ = Session.objects.get_or_create(
            group=group, date=day, defaults={'center': c, 'teacher': group.teacher})
        _, created = Attendance.objects.get_or_create(
            session=session, student=student,
            defaults={'center': c, 'status': 'present', 'marked_at': when, 'marked_by': request.user})
        # TODO: لو عندك دالة إرسال واتساب لولي الأمر عند الحضور، استدعها هنا (لو created)
        return 'created' if created else 'duplicate'

    if op.get('type') == 'payment':
        try:
            amount = Decimal(str(op['amount']))
        except (InvalidOperation, KeyError):
            raise ValueError('مبلغ غير صحيح')
        if amount <= 0:
            raise ValueError('مبلغ غير صحيح')
        month = (parse_date(op.get('month') or '') or current_month()).replace(day=1)
        method = op.get('method') if op.get('method') in Payment.Method.values else 'cash'
        _, created = Payment.objects.get_or_create(
            student=student, group=group, month=month,
            defaults={'center': c, 'amount': amount, 'method': method,
                      'paid_at': when, 'received_by': request.user})
        return 'created' if created else 'duplicate'

    raise ValueError('نوع عملية غير معروف')


@api
@require_POST
def sync(request):
    try:
        ops = json.loads(request.body)['ops']
    except Exception:
        return JsonResponse({'error': 'bad json'}, status=400)
    out = []
    for op in ops[:500]:
        try:
            with transaction.atomic():
                status = _apply(request, op)
            out.append({'uuid': op.get('uuid'), 'status': status})
        except Exception as e:
            out.append({'uuid': op.get('uuid'), 'status': 'error', 'error': str(e)[:200]})
    return JsonResponse({'results': out})
