from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Attendance, Enrollment, Group, Session, Student, current_month
from .tasks import send_attendance_message


def _session_or_404(request, pk):
    qs = Session.objects.for_center(request.center).select_related('group', 'teacher')
    if request.user.role == 'teacher':
        teacher = getattr(request.user, 'teacher_profile', None)
        if teacher:
            qs = qs.filter(teacher=teacher)
        else:
            qs = qs.none()
    return get_object_or_404(qs, pk=pk)


def _row_context(session, student, attendance=None):
    """بيانات صف الطالب في القائمة"""
    return {
        'session': session,
        'student': student,
        'attendance': attendance,
        'paid': student.has_paid(session.group, current_month()),
    }


# ---------- اختيار المجموعة ----------

@login_required
def attendance_home(request):
    today = timezone.localdate()
    groups = _teacher_groups(request)
    today_groups = [g for g in groups if today.weekday() in g.days]
    other_groups = [g for g in groups if today.weekday() not in g.days]
    return render(request, 'attendance/home.html', {
        'today': today, 'today_groups': today_groups, 'other_groups': other_groups,
    })


@login_required
@require_POST
def open_session(request, group_id):
    group = get_object_or_404(_teacher_groups(request), pk=group_id)
    session, _ = Session.objects.get_or_create(
        group=group, date=timezone.localdate(),
        defaults={'center': group.center, 'teacher': group.teacher})
    return redirect('session_detail', pk=session.pk)


# ---------- شاشة الحصة ----------

@login_required
def session_detail(request, pk):
    session = _session_or_404(request, pk)
    students = (Student.objects.for_center(request.center)
                .filter(enrollments__group=session.group, enrollments__is_active=True)
                .order_by('name'))
    att_map = {a.student_id: a for a in session.attendances.all()}
    rows = [_row_context(session, s, att_map.get(s.id)) for s in students]
    return render(request, 'attendance/session.html', {
        'session': session, 'rows': rows,
        'present_count': sum(1 for r in rows if r['attendance'] and
                             r['attendance'].status == Attendance.Status.PRESENT),
        'total': len(rows),
    })


# ---------- مسح الباركود (HTMX) ----------

@login_required
@require_POST
def scan(request, pk):
    session = _session_or_404(request, pk)
    code = request.POST.get('barcode', '').strip()
    ctx = {'session': session}

    if session.is_closed:
        ctx['error'] = 'الحصة دي مقفولة'
        return render(request, 'attendance/partials/scan_result.html', ctx)

    # ابحث بالباركود، ولو مش رقم ابحث بالاسم (للكتابة اليدوية)
    qs = Student.objects.for_center(request.center).filter(is_active=True)
    student = qs.filter(barcode=code).first() if code.isdigit() else None
    if not student and len(code) >= 3:
        matches = list(qs.filter(name__icontains=code)[:5])
        if len(matches) == 1:
            student = matches[0]
        elif len(matches) > 1:
            ctx['candidates'] = matches
            return render(request, 'attendance/partials/scan_result.html', ctx)

    if not student:
        ctx['error'] = f'مفيش طالب بالكود "{code}"'
        return render(request, 'attendance/partials/scan_result.html', ctx)

    if not Enrollment.objects.filter(student=student, group=session.group, is_active=True).exists():
        ctx.update(error=f'{student.name} مش مسجل في المجموعة دي', student=student)
        return render(request, 'attendance/partials/scan_result.html', ctx)

    return _mark(request, session, student, Attendance.Status.PRESENT, from_scan=True)


# ---------- تعليم يدوي من القائمة ----------

@login_required
@require_POST
def mark(request, pk, student_id):
    session = _session_or_404(request, pk)
    student = get_object_or_404(Student.objects.for_center(request.center), pk=student_id)
    status = request.POST.get('status', Attendance.Status.PRESENT)
    return _mark(request, session, student, status, from_scan=False)


def _mark(request, session, student, status, from_scan):
    att, created = Attendance.objects.get_or_create(
        session=session, student=student,
        defaults={'center': session.center, 'status': status, 'marked_by': request.user})

    changed = created
    if not created and att.status != status:
        att.status = status
        att.marked_at = timezone.now()
        att.marked_by = request.user
        att.message_sent = False
        att.save()
        changed = True

    # ابعت رسالة بس لو حصل تغيير فعلي ولما يبقى حاضر
    if changed and status == Attendance.Status.PRESENT:
        send_attendance_message.delay(att.pk)

    ctx = _row_context(session, student, att)
    ctx.update({
        'duplicate': not changed,
        'present_count': session.present_count,
        'total': session.enrolled_count,
    })
    template = 'attendance/partials/scan_result.html' if from_scan \
        else 'attendance/partials/student_row.html'
    return render(request, template, ctx)


# ---------- قفل الحصة: الباقي غياب + رسائل ----------

@login_required
@require_POST
def close_session(request, pk):
    session = _session_or_404(request, pk)
    if not session.is_closed:
        present_ids = session.attendances.values_list('student_id', flat=True)
        absent_students = Student.objects.filter(
            enrollments__group=session.group, enrollments__is_active=True
        ).exclude(id__in=present_ids)
        for s in absent_students:
            att = Attendance.objects.create(center=session.center, session=session, student=s,
                                            status=Attendance.Status.ABSENT, marked_by=request.user)
            send_attendance_message.delay(att.pk)
        session.is_closed = True
        session.closed_at = timezone.now()
        session.save(update_fields=['is_closed', 'closed_at'])
    return redirect('session_detail', pk=pk)

# ---------- تقييد المدرس ----------
def _teacher_groups(request):
    """لو المستخدم مدرس يرجع مجموعاته فقط، وإلا كل مجموعات السنتر"""
    qs = Group.objects.for_center(request.center).filter(is_active=True).select_related('teacher')
    if request.user.role == 'teacher':
        teacher = getattr(request.user, 'teacher_profile', None)
        if teacher:
            qs = qs.filter(teacher=teacher)
        else:
            qs = qs.none()
    return qs
