# core/admin.py
from django.contrib import admin
from .models import *

class EnrollmentInline(admin.TabularInline):
    model = Enrollment
    extra = 1

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('name', 'barcode', 'parent_phone', 'grade', 'center')
    search_fields = ('name', 'barcode', 'parent_phone')
    inlines = [EnrollmentInline]

for m in (Teacher, Group, Session, Attendance, Payment, Exam, ExamResult, MessageLog):
    admin.site.register(m)