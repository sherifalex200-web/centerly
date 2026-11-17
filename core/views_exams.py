"""
الامتحانات: تسجيل النتائج + إرسال واتساب
"""
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Enrollment, Exam, ExamResult, Group, Student
from .tasks import send_exam_result_message


def _teacher_groups(request):
    qs = Group.objects.for_center(request.center).filter(is_active=True).select_related('teacher')
    if request.user.role == 'teacher':
        teacher = getattr(request.user, 'teacher_profile', None)
        qs = qs.filter(teacher=teacher) if teacher else qs.none()
    return qs


@login_required
def exams_list(request):
    groups = _teacher_groups(request)
    exams = (
        Exam.objects.for_center(request.center)
        .filter(group__in=groups)
        .select_related('group', 'group__teacher')
        .order_by('-date')[:40]
    )
    return render(request, 'exams/list.html', {'exams': exams, 'groups': groups})


@login_required
def exam_create(request):
    groups = _teacher_groups(request)
    if request.method == 'POST':
        group = get_object_or_404(groups, pk=request.POST.get('group'))
        title = request.POST.get('title', '').strip()
        max_score = request.POST.get('max_score', '100')
        exam_date = request.POST.get('date') or timezone.localdate().isoformat()
        if not title:
            messages.error(request, 'عنوان الامتحان مطلوب')
            return redirect('exam_create')
        exam = Exam.objects.create(
            center=request.center,
            group=group,
            title=title,
            max_score=Decimal(max_score),
            date=exam_date,
        )
        messages.success(request, 'تم إنشاء الامتحان')
        return redirect('exam_detail', pk=exam.pk)
    return render(request, 'exams/create.html', {
        'groups': groups,
        'today': timezone.localdate().isoformat(),
    })


@login_required
def exam_detail(request, pk):
    groups = _teacher_groups(request)
    exam = get_object_or_404(
        Exam.objects.for_center(request.center).filter(group__in=groups),
        pk=pk,
    )
    students = (
        Student.objects.for_center(request.center)
        .filter(enrollments__group=exam.group, enrollments__is_active=True)
        .order_by('name')
    )
    results = {r.student_id: r for r in exam.results.all()}
    rows = []
    for s in students:
        r = results.get(s.id)
        rows.append({'student': s, 'result': r})
    return render(request, 'exams/detail.html', {
        'exam': exam,
        'rows': rows,
        'entered': sum(1 for r in rows if r['result']),
        'total': len(rows),
    })


@login_required
@require_POST
def exam_save_score(request, pk):
    groups = _teacher_groups(request)
    exam = get_object_or_404(
        Exam.objects.for_center(request.center).filter(group__in=groups),
        pk=pk,
    )
    student_id = request.POST.get('student_id')
    score_raw = request.POST.get('score', '').strip()
    student = get_object_or_404(
        Student.objects.for_center(request.center), pk=student_id
    )
    if score_raw == '':
        ExamResult.objects.filter(exam=exam, student=student).delete()
        result = None
    else:
        score = Decimal(score_raw)
        result, _ = ExamResult.objects.update_or_create(
            exam=exam, student=student,
            defaults={'center': request.center, 'score': score, 'message_sent': False},
        )
    if request.headers.get('HX-Request'):
        return render(request, 'exams/partials/score_row.html', {
            'exam': exam, 'student': student, 'result': result,
        })
    return redirect('exam_detail', pk=pk)


@login_required
@require_POST
def exam_send_results(request, pk):
    """إرسال نتائج الامتحان لأولياء الأمور"""
    groups = _teacher_groups(request)
    exam = get_object_or_404(
        Exam.objects.for_center(request.center).filter(group__in=groups),
        pk=pk,
    )
    results = exam.results.filter(message_sent=False).select_related('student')
    count = 0
    for r in results:
        if r.student.parent_phone:
            send_exam_result_message.delay(r.pk)
            count += 1
    messages.success(request, f'جاري إرسال {count} نتيجة واتساب')
    return redirect('exam_detail', pk=pk)
