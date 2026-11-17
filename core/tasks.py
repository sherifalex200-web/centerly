from celery import shared_task
from django.db.models import F
from django.utils import timezone

from accounts.models import Center
from .models import Attendance, MessageLog
from .services import whatsapp


# قوالب واتساب (لازم تتعملها وتتوافق عليها في Meta بنفس الأسماء)
# attendance_present: "حضر {{1}} حصة {{2}} مع {{3}} الساعة {{4}} - {{5}}"
# attendance_absent:  "تغيب {{1}} عن حصة {{2}} مع {{3}} بتاريخ {{4}} - {{5}}"

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_attendance_message(self, attendance_id):
    try:
        att = Attendance.objects.select_related(
            'student', 'center', 'session__group', 'session__teacher'
        ).get(pk=attendance_id)
    except Attendance.DoesNotExist:
        return

    center, student, session = att.center, att.student, att.session
    if att.message_sent or not student.parent_phone or not center.can_send_message:
        return

    local_time = timezone.localtime(att.marked_at)
    if att.status == Attendance.Status.ABSENT:
        template = 'attendance_absent'
        msg_type = MessageLog.Type.ABSENT
        params = [student.name, session.group.subject, session.teacher.name,
                  session.date.strftime('%d/%m'), center.sender_name]
        content = f'تغيب {student.name} عن حصة {session.group.subject} مع {session.teacher.name}'
    else:
        template = 'attendance_present'
        msg_type = MessageLog.Type.PRESENT
        params = [student.name, session.group.subject, session.teacher.name,
                  local_time.strftime('%I:%M %p'), center.sender_name]
        content = f'حضر {student.name} حصة {session.group.subject} مع {session.teacher.name}'

    log = MessageLog.objects.create(center=center, student=student, type=msg_type,
                                    to_phone=student.parent_phone, content=content)
    try:
        wamid = whatsapp.send_template(student.parent_phone, template, params)
    except Exception as exc:
        log.status = MessageLog.Status.FAILED
        log.error = str(exc)
        log.save(update_fields=['status', 'error'])
        raise self.retry(exc=exc)

    log.status = MessageLog.Status.SENT
    log.provider_message_id = wamid
    log.sent_at = timezone.now()
    log.save(update_fields=['status', 'provider_message_id', 'sent_at'])

    Attendance.objects.filter(pk=att.pk).update(message_sent=True)
    Center.objects.filter(pk=center.pk).update(messages_used=F('messages_used') + 1)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_payment_reminder(self, student_id, group_id=None):
    """تذكير ولي الأمر بدفع الاشتراك"""
    from .models import Student, Group, current_month

    try:
        student = Student.objects.select_related('center').get(pk=student_id)
    except Student.DoesNotExist:
        return

    center = student.center
    if not student.parent_phone or not center.can_send_message:
        return

    group = None
    if group_id:
        try:
            group = Group.objects.get(pk=group_id, center=center)
        except Group.DoesNotExist:
            pass

    month = current_month()
    month_label = month.strftime('%m/%Y')

    if group:
        fee = group.monthly_fee
        subject = group.subject
        content = f'تذكير: اشتراك {student.name} في {subject} لشهر {month_label} بقيمة {fee} ج لم يُسدد بعد - {center.sender_name}'
        params = [student.name, subject, month_label, str(fee), center.sender_name]
    else:
        content = f'تذكير: يرجى سداد اشتراك {student.name} لشهر {month_label} - {center.sender_name}'
        params = [student.name, month_label, center.sender_name]

    log = MessageLog.objects.create(
        center=center, student=student,
        type=MessageLog.Type.PAYMENT_REMINDER,
        to_phone=student.parent_phone, content=content,
    )
    try:
        # قالب واتساب: payment_reminder
        wamid = whatsapp.send_template(student.parent_phone, 'payment_reminder', params)
    except Exception as exc:
        log.status = MessageLog.Status.FAILED
        log.error = str(exc)
        log.save(update_fields=['status', 'error'])
        # في وضع التطوير مش هنعمل retry
        if not getattr(__import__('django.conf', fromlist=['settings']).settings, 'WHATSAPP_ENABLED', False):
            return
        raise self.retry(exc=exc)

    log.status = MessageLog.Status.SENT
    log.provider_message_id = wamid
    log.sent_at = timezone.now()
    log.save(update_fields=['status', 'provider_message_id', 'sent_at'])
    Center.objects.filter(pk=center.pk).update(messages_used=F('messages_used') + 1)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_exam_result_message(self, result_id):
    """إرسال نتيجة امتحان لولي الأمر"""
    from .models import ExamResult

    try:
        result = ExamResult.objects.select_related(
            'student', 'center', 'exam', 'exam__group'
        ).get(pk=result_id)
    except ExamResult.DoesNotExist:
        return

    center, student, exam = result.center, result.student, result.exam
    if result.message_sent or not student.parent_phone or not center.can_send_message:
        return

    content = (
        f'نتيجة {student.name} في {exam.title} ({exam.group.subject}): '
        f'{result.score}/{exam.max_score} - {center.sender_name}'
    )
    params = [
        student.name,
        exam.title,
        exam.group.subject,
        str(result.score),
        str(exam.max_score),
        center.sender_name,
    ]

    log = MessageLog.objects.create(
        center=center, student=student,
        type=MessageLog.Type.EXAM,
        to_phone=student.parent_phone, content=content,
    )
    try:
        wamid = whatsapp.send_template(student.parent_phone, 'exam_result', params)
    except Exception as exc:
        log.status = MessageLog.Status.FAILED
        log.error = str(exc)
        log.save(update_fields=['status', 'error'])
        from django.conf import settings
        if not settings.WHATSAPP_ENABLED:
            return
        raise self.retry(exc=exc)

    log.status = MessageLog.Status.SENT
    log.provider_message_id = wamid
    log.sent_at = timezone.now()
    log.save(update_fields=['status', 'provider_message_id', 'sent_at'])
    ExamResult.objects.filter(pk=result.pk).update(message_sent=True)
    Center.objects.filter(pk=center.pk).update(messages_used=F('messages_used') + 1)
