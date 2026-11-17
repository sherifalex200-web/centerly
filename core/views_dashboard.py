"""
لوحة التحكم الرئيسية + إعدادات السنتر
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import Center
from .models import (
    Attendance, Enrollment, Group, Payment, Session, Student, current_month,
)


@login_required
def dashboard(request):
    """الصفحة الرئيسية بعد الدخول"""
    center = request.center
    today = timezone.localdate()
    month = current_month()

    # حصص النهاردة (المدرس يشوف مجموعاته فقط)
    groups_qs = Group.objects.for_center(center).filter(is_active=True).select_related('teacher')
    if request.user.role == 'teacher':
        teacher = getattr(request.user, 'teacher_profile', None)
        groups_qs = groups_qs.filter(teacher=teacher) if teacher else groups_qs.none()
    groups_today = [g for g in groups_qs if today.weekday() in g.days]
    sessions_today = Session.objects.for_center(center).filter(date=today).select_related('group')
    sessions_map = {s.group_id: s for s in sessions_today}

    # إحصائيات سريعة
    total_students = Student.objects.for_center(center).filter(is_active=True).count()
    total_groups = Group.objects.for_center(center).filter(is_active=True).count()

    # تحصيل الشهر
    collected = (Payment.objects.for_center(center)
                 .filter(month=month)
                 .aggregate(total=Sum('amount'))['total'] or Decimal('0'))

    # متأخرين هذا الشهر (تقريبي)
    active_enrollments = Enrollment.objects.for_center(center).filter(is_active=True).count()
    paid_this_month = Payment.objects.for_center(center).filter(month=month).count()
    unpaid_approx = max(0, active_enrollments - paid_this_month)

    # حضور آخر 7 أيام
    week_ago = today - timedelta(days=7)
    recent_attendance = (
        Attendance.objects.for_center(center)
        .filter(session__date__gte=week_ago, status=Attendance.Status.PRESENT)
        .values('session__date')
        .annotate(count=Count('id'))
        .order_by('session__date')
    )

    # آخر الحصص
    recent_sessions = (
        Session.objects.for_center(center)
        .select_related('group', 'teacher')
        .order_by('-date')[:8]
    )

    return render(request, 'dashboard.html', {
        'today': today,
        'groups_today': groups_today,
        'sessions_map': sessions_map,
        'total_students': total_students,
        'total_groups': total_groups,
        'collected': collected,
        'unpaid_approx': unpaid_approx,
        'recent_sessions': recent_sessions,
        'month': month,
        'messages_used': center.messages_used,
        'messages_quota': center.messages_quota,
    })


@login_required
def center_settings(request):
    """إعدادات السنتر (لصاحب السنتر فقط)"""
    if not request.user.is_owner and not request.user.is_superuser:
        messages.error(request, 'غير مسموح')
        return redirect('dashboard')

    center = request.center

    if request.method == 'POST':
        center.name = request.POST.get('name', center.name).strip()
        center.phone = request.POST.get('phone', center.phone).strip()
        center.address = request.POST.get('address', center.address).strip()
        center.whatsapp_sender_name = request.POST.get('whatsapp_sender_name', '').strip()
        if 'logo' in request.FILES:
            center.logo = request.FILES['logo']
        center.save()
        messages.success(request, 'تم حفظ الإعدادات')
        return redirect('center_settings')

    return render(request, 'settings.html', {'center': center})
