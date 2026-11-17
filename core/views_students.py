"""
استيراد الطلاب من إكسل + طباعة الكروت
"""
import io
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from openpyxl import Workbook, load_workbook

from .models import Enrollment, Grade, Group, Student


# ---------- استيراد من إكسل ----------

@login_required
def students_import(request):
    """صفحة استيراد الطلاب من ملف إكسل"""
    groups = Group.objects.for_center(request.center).filter(is_active=True).select_related('teacher')
    return render(request, 'students/import.html', {'groups': groups})


@login_required
@require_POST
def students_import_upload(request):
    """معالجة ملف الإكسل"""
    file = request.FILES.get('file')
    group_id = request.POST.get('group')

    if not file:
        messages.error(request, 'لازم تختار ملف إكسل')
        return redirect('students_import')

    group = None
    if group_id:
        group = get_object_or_404(Group.objects.for_center(request.center), pk=group_id)

    try:
        wb = load_workbook(file, read_only=True, data_only=True)
        ws = wb.active
    except Exception as e:
        messages.error(request, f'الملف مش صالح: {e}')
        return redirect('students_import')

    # توقع الأعمدة: الاسم | تليفون ولي الأمر | الصف | تليفون الطالب | المدرسة | ملاحظات
    created = 0
    updated = 0
    errors = []
    grade_map = {v: k for k, v in Grade.choices}
    # كمان نقبل الكود الإنجليزي
    grade_map.update({k: k for k, _ in Grade.choices})

    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row or not row[0]:
            continue
        name = str(row[0]).strip()
        parent_phone = str(row[1] or '').strip().replace(' ', '')
        grade_raw = str(row[2] or '').strip()
        phone = str(row[3] or '').strip().replace(' ', '') if len(row) > 3 else ''
        school = str(row[4] or '').strip() if len(row) > 4 else ''
        notes = str(row[5] or '').strip() if len(row) > 5 else ''

        if not parent_phone:
            errors.append(f'سطر {i}: مفيش رقم ولي أمر لـ {name}')
            continue

        grade = grade_map.get(grade_raw)
        if not grade:
            # محاولة تخمين
            for code, label in Grade.choices:
                if grade_raw in label or label in grade_raw:
                    grade = code
                    break
            grade = grade or Grade.OTHER

        student, is_new = Student.objects.update_or_create(
            center=request.center,
            name=name,
            parent_phone=parent_phone,
            defaults={
                'grade': grade,
                'phone': phone,
                'school': school,
                'notes': notes,
                'is_active': True,
            }
        )
        if is_new:
            created += 1
        else:
            updated += 1

        if group:
            Enrollment.objects.get_or_create(
                center=request.center,
                student=student,
                group=group,
                defaults={'is_active': True}
            )

    msg = f'تم استيراد {created} طالب جديد'
    if updated:
        msg += f' وتحديث {updated}'
    if group:
        msg += f' وربطهم بمجموعة {group.name}'
    messages.success(request, msg)
    if errors:
        messages.warning(request, 'أخطاء: ' + ' | '.join(errors[:5]))
    return redirect('students_list')


@login_required
def students_import_template(request):
    """تحميل نموذج إكسل فاضي"""
    wb = Workbook()
    ws = wb.active
    ws.title = 'الطلاب'
    ws.append(['اسم الطالب', 'تليفون ولي الأمر', 'الصف', 'تليفون الطالب', 'المدرسة', 'ملاحظات'])
    ws.append(['أحمد محمد علي', '01012345678', 'أولى ثانوي', '01111111111', 'مدرسة النور', ''])
    ws.append(['سارة محمود', '01098765432', 'تانية إعدادي', '', '', 'طالب منقول'])

    # عرض الأعمدة
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 22

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="students_template.xlsx"'
    return response


# ---------- قائمة الطلاب ----------

@login_required
def students_list(request):
    students = (Student.objects.for_center(request.center)
                .filter(is_active=True)
                .prefetch_related('enrollments__group')
                .order_by('name'))
    q = request.GET.get('q', '').strip()
    if q:
        from django.db.models import Q
        students = students.filter(
            Q(name__icontains=q) | Q(barcode__icontains=q) | Q(parent_phone__icontains=q)
        )
    return render(request, 'students/list.html', {
        'students': students,
        'q': q,
        'total': students.count(),
    })


# ---------- طباعة كروت الطلاب ----------

@login_required
def student_cards(request):
    """اختيار الطلاب لطباعة الكروت"""
    students = (Student.objects.for_center(request.center)
                .filter(is_active=True).order_by('name'))
    group_id = request.GET.get('group')
    if group_id:
        students = students.filter(enrollments__group_id=group_id, enrollments__is_active=True)
    groups = Group.objects.for_center(request.center).filter(is_active=True)
    return render(request, 'students/cards.html', {
        'students': students,
        'groups': groups,
        'selected_group': group_id,
    })


@login_required
@require_POST
def student_cards_pdf(request):
    """توليد PDF لكروت الطلاب"""
    from .pdf_cards import generate_student_cards_pdf

    ids = request.POST.getlist('student_ids')
    if not ids:
        messages.error(request, 'اختار طالب واحد على الأقل')
        return redirect('student_cards')

    students = (Student.objects.for_center(request.center)
                .filter(pk__in=ids, is_active=True)
                .order_by('name'))

    pdf_bytes = generate_student_cards_pdf(students, request.center)

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="student_cards.pdf"'
    return response


# ---------- تفاصيل وتعديل طالب ----------

@login_required
def student_detail(request, pk):
    student = get_object_or_404(Student.objects.for_center(request.center), pk=pk)
    enrollments = student.enrollments.filter(is_active=True).select_related('group', 'group__teacher')
    recent_att = (
        student.attendances.select_related('session__group')
        .order_by('-session__date')[:15]
    )
    payments = student.payments.select_related('group').order_by('-month')[:12]
    return render(request, 'students/detail.html', {
        'student': student,
        'enrollments': enrollments,
        'recent_att': recent_att,
        'payments': payments,
        'groups': Group.objects.for_center(request.center).filter(is_active=True),
    })


@login_required
def student_edit(request, pk=None):
    """إضافة أو تعديل طالب"""
    center = request.center
    student = None
    if pk:
        student = get_object_or_404(Student.objects.for_center(center), pk=pk)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        parent_phone = request.POST.get('parent_phone', '').strip()
        grade = request.POST.get('grade', Grade.OTHER)
        phone = request.POST.get('phone', '').strip()
        school = request.POST.get('school', '').strip()
        notes = request.POST.get('notes', '').strip()
        group_ids = request.POST.getlist('groups')

        if not name or not parent_phone:
            messages.error(request, 'الاسم ورقم ولي الأمر مطلوبين')
            return redirect(request.path)

        if student:
            student.name = name
            student.parent_phone = parent_phone
            student.grade = grade
            student.phone = phone
            student.school = school
            student.notes = notes
            student.save()
            messages.success(request, 'تم تحديث بيانات الطالب')
        else:
            student = Student.objects.create(
                center=center, name=name, parent_phone=parent_phone,
                grade=grade, phone=phone, school=school, notes=notes,
            )
            messages.success(request, f'تم إضافة {name} — الباركود: {student.barcode}')

        # تحديث المجموعات
        current = set(student.enrollments.filter(is_active=True).values_list('group_id', flat=True))
        wanted = set(int(g) for g in group_ids if g)
        # إلغاء اللي اتشال
        student.enrollments.filter(group_id__in=current - wanted).update(is_active=False)
        # إضافة الجديد
        for gid in wanted - current:
            Enrollment.objects.update_or_create(
                center=center, student=student, group_id=gid,
                defaults={'is_active': True}
            )
        # إعادة تفعيل لو كان متوقف
        student.enrollments.filter(group_id__in=wanted, is_active=False).update(is_active=True)

        return redirect('student_detail', pk=student.pk)

    enrolled_ids = []
    if student:
        enrolled_ids = list(
            student.enrollments.filter(is_active=True).values_list('group_id', flat=True)
        )

    return render(request, 'students/edit.html', {
        'student': student,
        'grades': Grade.choices,
        'groups': Group.objects.for_center(center).filter(is_active=True).select_related('teacher'),
        'enrolled_ids': enrolled_ids,
    })
