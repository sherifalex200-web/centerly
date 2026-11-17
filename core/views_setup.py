"""
إدارة المدرسين والمجموعات من لوحة العميل
"""
from datetime import time
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import DAY_CHOICES, Grade, Group, Teacher


def _require_staff(request):
    """المدرس العادي لا يدير الهيكل"""
    if getattr(request.user, 'role', None) == 'teacher' and not request.user.is_superuser:
        messages.error(request, 'غير مسموح — تواصل مع إدارة السنتر')
        return False
    return True


# ---------- المدرسين ----------

@login_required
def teachers_list(request):
    if not _require_staff(request):
        return redirect('dashboard')
    teachers = (
        Teacher.objects.for_center(request.center)
        .order_by('-is_active', 'name')
    )
    return render(request, 'setup/teachers.html', {'teachers': teachers})


@login_required
def teacher_edit(request, pk=None):
    if not _require_staff(request):
        return redirect('dashboard')
    center = request.center
    teacher = None
    if pk:
        teacher = get_object_or_404(Teacher.objects.for_center(center), pk=pk)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        subject = request.POST.get('subject', '').strip()
        phone = request.POST.get('phone', '').strip()
        percentage = request.POST.get('percentage', '70')
        is_active = request.POST.get('is_active') == '1'

        if not name or not subject:
            messages.error(request, 'الاسم والمادة مطلوبين')
            return redirect(request.path)

        try:
            percentage = Decimal(percentage)
        except (InvalidOperation, TypeError):
            percentage = Decimal('70')

        if teacher:
            teacher.name = name
            teacher.subject = subject
            teacher.phone = phone
            teacher.percentage = percentage
            teacher.is_active = is_active
            teacher.save()
            messages.success(request, 'تم تحديث بيانات المدرس')
        else:
            Teacher.objects.create(
                center=center,
                name=name,
                subject=subject,
                phone=phone,
                percentage=percentage,
                is_active=True,
            )
            messages.success(request, f'تم إضافة المدرس {name}')
        return redirect('teachers_list')

    return render(request, 'setup/teacher_form.html', {'teacher': teacher})


@login_required
@require_POST
def teacher_toggle(request, pk):
    if not _require_staff(request):
        return redirect('dashboard')
    teacher = get_object_or_404(Teacher.objects.for_center(request.center), pk=pk)
    teacher.is_active = not teacher.is_active
    teacher.save(update_fields=['is_active'])
    messages.info(request, f'{"تم تفعيل" if teacher.is_active else "تم إيقاف"} {teacher.name}')
    return redirect('teachers_list')


# ---------- المجموعات ----------

@login_required
def groups_list(request):
    if not _require_staff(request):
        return redirect('dashboard')
    groups = (
        Group.objects.for_center(request.center)
        .select_related('teacher')
        .order_by('-is_active', 'grade', 'name')
    )
    return render(request, 'setup/groups.html', {'groups': groups})


@login_required
def group_edit(request, pk=None):
    if not _require_staff(request):
        return redirect('dashboard')
    center = request.center
    group = None
    if pk:
        group = get_object_or_404(Group.objects.for_center(center), pk=pk)

    teachers = Teacher.objects.for_center(center).filter(is_active=True).order_by('name')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        subject = request.POST.get('subject', '').strip()
        grade = request.POST.get('grade', Grade.OTHER)
        teacher_id = request.POST.get('teacher')
        start_time_raw = request.POST.get('start_time', '16:00')
        monthly_fee = request.POST.get('monthly_fee', '0')
        session_fee = request.POST.get('session_fee', '0')
        days = request.POST.getlist('days')
        is_active = request.POST.get('is_active') == '1'

        if not name or not subject or not teacher_id:
            messages.error(request, 'الاسم والمادة والمدرس مطلوبين')
            return redirect(request.path)

        teacher = get_object_or_404(Teacher.objects.for_center(center), pk=teacher_id)

        try:
            parts = start_time_raw.split(':')
            start_time = time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        except (ValueError, IndexError):
            start_time = time(16, 0)

        try:
            monthly_fee = Decimal(monthly_fee)
        except (InvalidOperation, TypeError):
            monthly_fee = Decimal('0')
        try:
            session_fee = Decimal(session_fee)
        except (InvalidOperation, TypeError):
            session_fee = Decimal('0')

        days_int = []
        for d in days:
            try:
                days_int.append(int(d))
            except ValueError:
                pass

        if group:
            group.name = name
            group.subject = subject
            group.grade = grade
            group.teacher = teacher
            group.start_time = start_time
            group.monthly_fee = monthly_fee
            group.session_fee = session_fee
            group.days = days_int
            group.is_active = is_active
            group.save()
            messages.success(request, 'تم تحديث المجموعة')
        else:
            Group.objects.create(
                center=center,
                teacher=teacher,
                name=name,
                subject=subject,
                grade=grade,
                start_time=start_time,
                monthly_fee=monthly_fee,
                session_fee=session_fee,
                days=days_int,
                is_active=True,
            )
            messages.success(request, f'تم إنشاء مجموعة {name}')
        return redirect('groups_list')

    selected_days = group.days if group else []
    start_value = group.start_time.strftime('%H:%M') if group and group.start_time else '16:00'

    return render(request, 'setup/group_form.html', {
        'group': group,
        'teachers': teachers,
        'grades': Grade.choices,
        'day_choices': DAY_CHOICES,
        'selected_days': selected_days,
        'start_value': start_value,
    })


@login_required
@require_POST
def group_toggle(request, pk):
    if not _require_staff(request):
        return redirect('dashboard')
    group = get_object_or_404(Group.objects.for_center(request.center), pk=pk)
    group.is_active = not group.is_active
    group.save(update_fields=['is_active'])
    messages.info(request, f'{"تم تفعيل" if group.is_active else "تم إيقاف"} {group.name}')
    return redirect('groups_list')
