from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone


class Center(models.Model):
    class Plan(models.TextChoices):
        TRIAL = 'trial', 'تجريبي'
        STARTER = 'starter', 'بداية'
        GROWTH = 'growth', 'نمو'
        PRO = 'pro', 'احترافي'

    name = models.CharField('اسم السنتر', max_length=120)
    phone = models.CharField('تليفون', max_length=20)
    address = models.CharField('العنوان', max_length=255, blank=True)
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)
    whatsapp_sender_name = models.CharField(
        'الاسم في رسائل واتساب', max_length=60, blank=True,
        help_text='لو فاضي هيستخدم اسم السنتر')

    plan = models.CharField('الخطة', max_length=20, choices=Plan.choices, default=Plan.TRIAL)
    subscription_end = models.DateField('نهاية الاشتراك')
    is_active = models.BooleanField('مفعّل', default=True)
    messages_quota = models.PositiveIntegerField('رصيد الرسائل الشهري', default=300)
    messages_used = models.PositiveIntegerField('الرسائل المستخدمة', default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'سنتر'
        verbose_name_plural = 'السناتر'

    def __str__(self):
        return self.name

    @property
    def subscription_active(self):
        return self.is_active and self.subscription_end >= timezone.localdate()

    @property
    def can_send_message(self):
        return self.messages_used < self.messages_quota

    @property
    def sender_name(self):
        return self.whatsapp_sender_name or self.name


class UserManager(BaseUserManager):
    def create_user(self, phone, password=None, **extra):
        if not phone:
            raise ValueError('رقم التليفون مطلوب')
        user = self.model(phone=phone, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra):
        extra.setdefault('is_staff', True)
        extra.setdefault('is_superuser', True)
        extra.setdefault('role', User.Role.OWNER)
        extra.setdefault('name', 'Admin')
        return self.create_user(phone, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """تسجيل الدخول برقم التليفون"""
    class Role(models.TextChoices):
        OWNER = 'owner', 'صاحب السنتر'
        STAFF = 'staff', 'موظف'
        TEACHER = 'teacher', 'مدرس'

    center = models.ForeignKey(Center, on_delete=models.CASCADE, related_name='users',
                               null=True, blank=True)
    phone = models.CharField('رقم التليفون', max_length=15, unique=True)
    name = models.CharField('الاسم', max_length=100)
    role = models.CharField('الدور', max_length=10, choices=Role.choices, default=Role.STAFF)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = 'phone'
    REQUIRED_FIELDS = ['name']
    objects = UserManager()

    class Meta:
        verbose_name = 'مستخدم'
        verbose_name_plural = 'المستخدمين'

    def __str__(self):
        return f'{self.name} ({self.phone})'

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER