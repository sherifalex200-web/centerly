"""
شاشة الأقساط: تسجيل دفعة + المتأخرين + تذكير جماعي
"""
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Enrollment, Group, MessageLog, Payment, Student, current_month
from .tasks import send_payment_reminder


@login_required
def payments_home(request):
    """الشاشة الرئيسية للأقساط"""
    month = current_month()
    month_param = request.GET.get('month')
    if month_param:
        try:
            y, m = month_param.split('-')
            month = date(int(y), int(m), 1)
        except (ValueError, TypeError):
            pass

    groups = Group.objects.for_center(request.center).filter(is_active=True).select_related('teacher')
    group_id = request.GET.get('group')
    selected_group = None
    if group_id:
        selected_group = get_object_or_404(groups, pk=group_id)

    # الطلاب المسجلين في المجموعة (أو كل الطلاب لو مفيش مجموعة)
    if selected_group:
        enrollments = (Enrollment.objects.for_center(request.center)
                       .filter(group=selected_group, is_active=True)
                       .select_related('student'))
        students = [e.student for e in enrollments]
    else:
        students = list(Student.objects.for_center(request.center).filter(is_active=True))

    # المدفوعات لهذا الشهر
    paid_qs = Payment.objects.for_center(request.center).filter(month=month)
    if selected_group:
        paid_qs = paid_qs.filter(group=selected_group)
    paid_map = {(p.student_id, p.group_id): p for p in paid_qs}

    rows = []
    unpaid_count = 0
    total_expected = Decimal('0')
    total_collected = Decimal('0')

    for student in students:
        if selected_group:
            groups_to_check = [selected_group]
        else:
            groups_to_check = [e.group for e in student.enrollments.filter(is_active=True).select_related('group')]

        for g in groups_to_check:
            payment = paid_map.get((student.id, g.id))
            is_paid = payment is not None
            if not is_paid:
                unpaid_count += 1
                total_expected += g.monthly_fee
            else:
                total_collected += payment.amount

            rows.append({
                'student': student,
                'group': g,
                'payment': payment,
                'is_paid': is_paid,
                'fee': g.monthly_fee,
            })

    # ترتيب: المتأخرين الأول
    rows.sort(key=lambda r: (r['is_paid'], r['student'].name))

    return render(request, 'payments/home.html', {
        'rows': rows,
        'groups': groups,
        'selected_group': selected_group,
        'month': month,
        'unpaid_count': unpaid_count,
        'total_expected': total_expected,
        'total_collected': total_collected,
        'total_students': len(set(r['student'].id for r in rows)),
    })


@login_required
@require_POST
def payment_mark(request):
    """تسجيل دفعة لطالب"""
    student_id = request.POST.get('student_id')
    group_id = request.POST.get('group_id')
    amount = request.POST.get('amount')
    method = request.POST.get('method', Payment.Method.CASH)
    note = request.POST.get('note', '')

    student = get_object_or_404(Student.objects.for_center(request.center), pk=student_id)
    group = get_object_or_404(Group.objects.for_center(request.center), pk=group_id)
    month = current_month()

    try:
        amount = Decimal(amount)
    except Exception:
        amount = group.monthly_fee

    payment, created = Payment.objects.update_or_create(
        student=student,
        group=group,
        month=month,
        defaults={
            'center': request.center,
            'amount': amount,
            'method': method,
            'received_by': request.user,
            'note': note,
            'paid_at': timezone.now(),
        }
    )

    if created:
        messages.success(request, f'تم تسجيل دفعة {student.name} — {amount} ج')
    else:
        messages.info(request, f'تم تحديث دفعة {student.name}')

    # لو جاي من HTMX نرجع جزء من الصفحة
    if request.headers.get('HX-Request'):
        return render(request, 'payments/partials/row.html', {
            'student': student,
            'group': group,
            'payment': payment,
            'is_paid': True,
            'fee': group.monthly_fee,
        })

    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or '/payments/'
    return redirect(next_url)


@login_required
@require_POST
def payment_remind(request):
    """إرسال تذكير دفع لطالب واحد أو جماعي"""
    student_ids = request.POST.getlist('student_ids')
    group_id = request.POST.get('group_id')

    if not student_ids:
        messages.warning(request, 'مفيش طلاب مختارين')
        return redirect('payments_home')

    group = None
    if group_id:
        group = get_object_or_404(Group.objects.for_center(request.center), pk=group_id)

    month = current_month()
    sent = 0
    for sid in student_ids:
        student = Student.objects.for_center(request.center).filter(pk=sid).first()
        if not student or not student.parent_phone:
            continue
        # تأكد إنه فعلاً متأخر
        if group and student.has_paid(group, month):
            continue
        send_payment_reminder.delay(student.id, group.id if group else None)
        sent += 1

    messages.success(request, f'اتبعتت {sent} رسالة تذكير')
    return redirect(request.META.get('HTTP_REFERER', '/payments/'))
