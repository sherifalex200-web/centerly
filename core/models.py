import secrets
from datetime import date

from django.conf import settings
from django.db import models
from django.utils import timezone

# ---------- الأساس: كل جدول مرتبط بسنتر ----------

class CenterQuerySet(models.QuerySet):
    def for_center(self, center):
        return self.filter(center=center)


class CenterOwnedModel(models.Model):
    center = models.ForeignKey('accounts.Center', on_delete=models.CASCADE,
                               related_name='%(class)ss')
    created_at = models.DateTimeField(auto_now_add=True)
    objects = CenterQuerySet.as_manager()

    class Meta:
        abstract = True


# ---------- الثوابت ----------

# أرقام Python weekday: Monday=0 ... Sunday=6
DAY_CHOICES = [
    (5, 'السبت'), (6, 'الأحد'), (0, 'الاثنين'), (1, 'الثلاثاء'),
    (2, 'الأربعاء'), (3, 'الخميس'), (4, 'الجمعة'),
]
DAY_NAMES = dict(DAY_CHOICES)


class Grade(models.TextChoices):
    PREP1 = 'p1', 'أولى إعدادي'
    PREP2 = 'p2', 'تانية إعدادي'
    PREP3 = 'p3', 'تالتة إعدادي'
    SEC1 = 's1', 'أولى ثانوي'
    SEC2 = 's2', 'تانية ثانوي'
    SEC3 = 's3', 'تالتة ثانوي'
    OTHER = 'ot', 'أخرى'


def current_month():
    today = timezone.localdate()
    return date(today.year, today.month, 1)


# ---------- المدرس ----------

class Teacher(CenterOwnedModel):
    name = models.CharField('الاسم', max_length=100)
    phone = models.CharField('التليفون', max_length=15, blank=True)
    subject = models.CharField('المادة', max_length=60)
    percentage = models.DecimalField('نسبة المدرس %', max_digits=5, decimal_places=2, default=70)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='teacher_profile')
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'مدرس'
        verbose_name_plural = 'المدرسين'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} - {self.subject}'


# ---------- المجموعة ----------

class Group(CenterOwnedModel):
    teacher = models.ForeignKey(Teacher, on_delete=models.PROTECT, related_name='groups')
    name = models.CharField('اسم المجموعة', max_length=100)
    subject = models.CharField('المادة', max_length=60)
    grade = models.CharField('الصف', max_length=2, choices=Grade.choices)
    days = models.JSONField('أيام الحصص', default=list, help_text='مثال: [5, 1] = السبت والثلاثاء')
    start_time = models.TimeField('معاد الحصة')
    monthly_fee = models.DecimalField('الاشتراك الشهري', max_digits=8, decimal_places=2)
    session_fee = models.DecimalField('سعر الحصة الواحدة', max_digits=8, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'مجموعة'
        verbose_name_plural = 'المجموعات'
        ordering = ['grade', 'name']

    def __str__(self):
        return f'{self.name} - {self.subject} ({self.get_grade_display()})'

    @property
    def days_display(self):
        return ' / '.join(DAY_NAMES.get(d, '') for d in self.days)

    def has_session_today(self):
        return timezone.localdate().weekday() in self.days

    @property
    def active_students_count(self):
        return self.enrollments.filter(is_active=True).count()


# ---------- الطالب ----------

def generate_barcode():
    return ''.join(secrets.choice('0123456789') for _ in range(8))


class Student(CenterOwnedModel):
    name = models.CharField('اسم الطالب', max_length=120)
    phone = models.CharField('تليفون الطالب', max_length=15, blank=True)
    parent_phone = models.CharField('تليفون ولي الأمر', max_length=15)
    grade = models.CharField('الصف', max_length=2, choices=Grade.choices)
    school = models.CharField('المدرسة', max_length=120, blank=True)
    barcode = models.CharField('الباركود', max_length=12, unique=True, blank=True)
    notes = models.TextField('ملاحظات', blank=True)
    is_active = models.BooleanField(default=True)

    groups = models.ManyToManyField(Group, through='Enrollment', related_name='students')

    class Meta:
        verbose_name = 'طالب'
        verbose_name_plural = 'الطلاب'
        ordering = ['name']
        indexes = [
            models.Index(fields=['center', 'name']),
            models.Index(fields=['center', 'parent_phone']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.barcode:
            code = generate_barcode()
            while Student.objects.filter(barcode=code).exists():
                code = generate_barcode()
            self.barcode = code
        super().save(*args, **kwargs)

    def has_paid(self, group, month=None):
        month = month or current_month()
        return self.payments.filter(group=group, month=month).exists()

    def unpaid_groups(self, month=None):
        month = month or current_month()
        paid_ids = self.payments.filter(month=month).values_list('group_id', flat=True)
        return Group.objects.filter(enrollments__student=self, enrollments__is_active=True
                                    ).exclude(id__in=paid_ids)


class Enrollment(CenterOwnedModel):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='enrollments')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='enrollments')
    joined_at = models.DateField('تاريخ الانضمام', default=timezone.localdate)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'تسجيل في مجموعة'
        verbose_name_plural = 'التسجيلات'
        unique_together = ('student', 'group')

    def __str__(self):
        return f'{self.student} ← {self.group}'

    def save(self, *args, **kwargs):
        self.center_id = self.center_id or self.student.center_id
        super().save(*args, **kwargs)


# ---------- الحصة والحضور ----------

class Session(CenterOwnedModel):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='sessions')
    teacher = models.ForeignKey(Teacher, on_delete=models.PROTECT, related_name='sessions')
    date = models.DateField('التاريخ', default=timezone.localdate)
    notes = models.CharField('ملاحظات', max_length=255, blank=True)
    is_closed = models.BooleanField('الحصة مقفولة', default=False)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'حصة'
        verbose_name_plural = 'الحصص'
        unique_together = ('group', 'date')
        ordering = ['-date']

    def __str__(self):
        return f'{self.group.name} - {self.date}'

    @property
    def present_count(self):
        return self.attendances.filter(status=Attendance.Status.PRESENT).count()

    @property
    def enrolled_count(self):
        return self.group.enrollments.filter(is_active=True).count()


class Attendance(CenterOwnedModel):
    class Status(models.TextChoices):
        PRESENT = 'present', 'حاضر'
        ABSENT = 'absent', 'غائب'
        LATE = 'late', 'متأخر'

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='attendances')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendances')
    status = models.CharField('الحالة', max_length=10, choices=Status.choices, default=Status.PRESENT)
    marked_at = models.DateTimeField('وقت التسجيل', default=timezone.now)
    marked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                  null=True, blank=True)
    message_sent = models.BooleanField('اتبعتت رسالة', default=False)

    class Meta:
        verbose_name = 'حضور'
        verbose_name_plural = 'سجل الحضور'
        unique_together = ('session', 'student')

    def __str__(self):
        return f'{self.student} - {self.session} - {self.get_status_display()}'

    def save(self, *args, **kwargs):
        self.center_id = self.center_id or self.session.center_id
        super().save(*args, **kwargs)


# ---------- الأقساط ----------

class Payment(CenterOwnedModel):
    class Method(models.TextChoices):
        CASH = 'cash', 'كاش'
        WALLET = 'wallet', 'محفظة'
        INSTAPAY = 'instapay', 'إنستاباي'

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='payments')
    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name='payments')
    month = models.DateField('الشهر', default=current_month, help_text='أول يوم في الشهر')
    amount = models.DecimalField('المبلغ', max_digits=8, decimal_places=2)
    method = models.CharField('طريقة الدفع', max_length=10, choices=Method.choices, default=Method.CASH)
    paid_at = models.DateTimeField('وقت الدفع', default=timezone.now)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = 'دفعة'
        verbose_name_plural = 'المدفوعات'
        unique_together = ('student', 'group', 'month')
        ordering = ['-paid_at']

    def __str__(self):
        return f'{self.student} - {self.group.name} - {self.month:%Y/%m} - {self.amount}'

    def save(self, *args, **kwargs):
        self.month = self.month.replace(day=1)
        self.center_id = self.center_id or self.student.center_id
        super().save(*args, **kwargs)


# ---------- الامتحانات ----------

class Exam(CenterOwnedModel):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='exams')
    title = models.CharField('العنوان', max_length=120)
    date = models.DateField('التاريخ', default=timezone.localdate)
    max_score = models.DecimalField('الدرجة الكلية', max_digits=6, decimal_places=2)

    class Meta:
        verbose_name = 'امتحان'
        verbose_name_plural = 'الامتحانات'
        ordering = ['-date']

    def __str__(self):
        return f'{self.title} - {self.group.name}'


class ExamResult(CenterOwnedModel):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='results')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='exam_results')
    score = models.DecimalField('الدرجة', max_digits=6, decimal_places=2)
    message_sent = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'نتيجة'
        verbose_name_plural = 'النتائج'
        unique_together = ('exam', 'student')

    def save(self, *args, **kwargs):
        self.center_id = self.center_id or self.exam.center_id
        super().save(*args, **kwargs)


# ---------- سجل الرسائل ----------

class MessageLog(CenterOwnedModel):
    class Type(models.TextChoices):
        PRESENT = 'present', 'حضور'
        ABSENT = 'absent', 'غياب'
        PAYMENT_REMINDER = 'pay_reminder', 'تذكير دفع'
        PAYMENT_RECEIPT = 'pay_receipt', 'إيصال دفع'
        EXAM = 'exam', 'نتيجة امتحان'
        BROADCAST = 'broadcast', 'رسالة جماعية'

    class Status(models.TextChoices):
        PENDING = 'pending', 'في الانتظار'
        SENT = 'sent', 'اتبعتت'
        DELIVERED = 'delivered', 'اتسلمت'
        READ = 'read', 'اتقرت'
        FAILED = 'failed', 'فشلت'

    student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='messages')
    type = models.CharField(max_length=20, choices=Type.choices)
    to_phone = models.CharField(max_length=15)
    content = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    provider_message_id = models.CharField(max_length=100, blank=True)  # wamid من واتساب
    error = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'رسالة'
        verbose_name_plural = 'سجل الرسائل'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['provider_message_id'])]

    def __str__(self):
        return f'{self.get_type_display()} → {self.to_phone} ({self.get_status_display()})'