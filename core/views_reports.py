"""
التقارير: حضور + تحصيل
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import (
    Attendance, Enrollment, Group, Payment, Session, Student, current_month,
)


@login_required
def reports_home(request):
    return render(request, 'reports/home.html')


@login_required
def report_attendance(request):
    """تقرير حضور مجموعة في فترة"""
    center = request.center
    groups = Group.objects.for_center(center).filter(is_active=True).select_related('teacher')

    group_id = request.GET.get('group')
    date_from = request.GET.get('from')
    date_to = request.GET.get('to')

    today = timezone.localdate()
    if not date_from:
        date_from = (today - timedelta(days=30)).isoformat()
    if not date_to:
        date_to = today.isoformat()

    selected_group = None
    rows = []
    sessions = []

    if group_id:
        selected_group = get_object_or_404(groups, pk=group_id)
        sessions = list(
            Session.objects.for_center(center)
            .filter(group=selected_group, date__gte=date_from, date__lte=date_to)
            .order_by('date')
        )
        students = (
            Student.objects.for_center(center)
            .filter(enrollments__group=selected_group, enrollments__is_active=True)
            .order_by('name')
        )
        att_qs = (
            Attendance.objects.for_center(center)
            .filter(session__in=sessions)
            .select_related('session')
        )
        att_map = {(a.student_id, a.session_id): a for a in att_qs}

        for student in students:
            present = 0
            absent = 0
            cells = []
            for sess in sessions:
                att = att_map.get((student.id, sess.id))
                if att and att.status == Attendance.Status.PRESENT:
                    present += 1
                    cells.append('P')
                elif att and att.status == Attendance.Status.ABSENT:
                    absent += 1
                    cells.append('A')
                else:
                    cells.append('-')
            total = present + absent
            pct = round(present * 100 / total, 1) if total else 0
            rows.append({
                'student': student,
                'present': present,
                'absent': absent,
                'pct': pct,
                'cells': cells,
            })

    return render(request, 'reports/attendance.html', {
        'groups': groups,
        'selected_group': selected_group,
        'date_from': date_from,
        'date_to': date_to,
        'sessions': sessions,
        'rows': rows,
    })


@login_required
def report_payments(request):
    """تقرير التحصيل الشهري"""
    center = request.center
    month = current_month()
    month_param = request.GET.get('month')
    if month_param:
        try:
            y, m = month_param.split('-')
            month = date(int(y), int(m), 1)
        except (ValueError, TypeError):
            pass

    groups = Group.objects.for_center(center).filter(is_active=True).select_related('teacher')

    # ملخص لكل مجموعة
    summary = []
    grand_expected = Decimal('0')
    grand_collected = Decimal('0')

    for g in groups:
        enrolled = Enrollment.objects.for_center(center).filter(group=g, is_active=True).count()
        expected = g.monthly_fee * enrolled
        collected = (
            Payment.objects.for_center(center)
            .filter(group=g, month=month)
            .aggregate(t=Sum('amount'))['t'] or Decimal('0')
        )
        paid_count = Payment.objects.for_center(center).filter(group=g, month=month).count()
        grand_expected += expected
        grand_collected += collected
        summary.append({
            'group': g,
            'enrolled': enrolled,
            'expected': expected,
            'collected': collected,
            'paid_count': paid_count,
            'unpaid_count': enrolled - paid_count,
            'pct': round(float(collected) * 100 / float(expected), 1) if expected else 0,
        })

    # آخر المدفوعات
    recent_payments = (
        Payment.objects.for_center(center)
        .filter(month=month)
        .select_related('student', 'group', 'received_by')
        .order_by('-paid_at')[:30]
    )

    return render(request, 'reports/payments.html', {
        'month': month,
        'summary': summary,
        'grand_expected': grand_expected,
        'grand_collected': grand_collected,
        'grand_remaining': grand_expected - grand_collected,
        'recent_payments': recent_payments,
    })


@login_required
def export_attendance_excel(request):
    """تصدير تقرير الحضور إكسل"""
    import io
    from openpyxl import Workbook
    from django.http import HttpResponse

    center = request.center
    group_id = request.GET.get('group')
    date_from = request.GET.get('from')
    date_to = request.GET.get('to')
    if not group_id:
        messages.error(request, 'اختار مجموعة أولاً')
        return redirect('report_attendance')

    group = get_object_or_404(Group.objects.for_center(center), pk=group_id)
    sessions = list(
        Session.objects.for_center(center)
        .filter(group=group, date__gte=date_from, date__lte=date_to)
        .order_by('date')
    )
    students = (
        Student.objects.for_center(center)
        .filter(enrollments__group=group, enrollments__is_active=True)
        .order_by('name')
    )
    att_qs = Attendance.objects.for_center(center).filter(session__in=sessions)
    att_map = {(a.student_id, a.session_id): a for a in att_qs}

    wb = Workbook()
    ws = wb.active
    ws.title = 'حضور'
    header = ['الطالب', 'الباركود', 'حاضر', 'غائب', 'النسبة']
    header += [s.date.strftime('%d/%m') for s in sessions]
    ws.append(header)

    for student in students:
        present = absent = 0
        cells = []
        for sess in sessions:
            att = att_map.get((student.id, sess.id))
            if att and att.status == Attendance.Status.PRESENT:
                present += 1
                cells.append('حاضر')
            elif att and att.status == Attendance.Status.ABSENT:
                absent += 1
                cells.append('غائب')
            else:
                cells.append('-')
        total = present + absent
        pct = round(present * 100 / total, 1) if total else 0
        ws.append([student.name, student.barcode, present, absent, f'{pct}%'] + cells)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="attendance_{group.name}.xlsx"'
    return response


@login_required
def export_payments_excel(request):
    """تصدير تقرير التحصيل إكسل"""
    import io
    from openpyxl import Workbook
    from django.http import HttpResponse
    from datetime import date as date_cls

    center = request.center
    month = current_month()
    month_param = request.GET.get('month')
    if month_param:
        try:
            y, m = month_param.split('-')
            month = date_cls(int(y), int(m), 1)
        except (ValueError, TypeError):
            pass

    groups = Group.objects.for_center(center).filter(is_active=True)
    wb = Workbook()
    ws = wb.active
    ws.title = 'تحصيل'
    ws.append(['المجموعة', 'المادة', 'عدد الطلاب', 'المطلوب', 'المحصّل', 'متأخرين', 'النسبة'])

    for g in groups:
        enrolled = Enrollment.objects.for_center(center).filter(group=g, is_active=True).count()
        expected = g.monthly_fee * enrolled
        collected = (
            Payment.objects.for_center(center)
            .filter(group=g, month=month)
            .aggregate(t=Sum('amount'))['t'] or Decimal('0')
        )
        paid_count = Payment.objects.for_center(center).filter(group=g, month=month).count()
        pct = round(float(collected) * 100 / float(expected), 1) if expected else 0
        ws.append([
            g.name, g.subject, enrolled,
            float(expected), float(collected),
            enrolled - paid_count, f'{pct}%',
        ])

    # ورقة المدفوعات التفصيلية
    ws2 = wb.create_sheet('تفاصيل')
    ws2.append(['الطالب', 'المجموعة', 'المبلغ', 'الطريقة', 'التاريخ', 'ملاحظة'])
    payments = (
        Payment.objects.for_center(center)
        .filter(month=month)
        .select_related('student', 'group')
        .order_by('-paid_at')
    )
    for p in payments:
        ws2.append([
            p.student.name, p.group.name, float(p.amount),
            p.get_method_display(), p.paid_at.strftime('%d/%m/%Y %H:%M'), p.note,
        ])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="payments_{month:%Y_%m}.xlsx"'
    return response
