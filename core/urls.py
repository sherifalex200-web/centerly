# core/urls.py
from django.urls import path
from . import views
from . import views_students
from . import views_payments
from . import views_dashboard
from . import views_reports
from . import views_exams
from . import views_setup

urlpatterns = [
    # لوحة التحكم
    path('', views_dashboard.dashboard, name='dashboard'),
    path('settings/', views_dashboard.center_settings, name='center_settings'),

    # الحضور
    path('attendance/', views.attendance_home, name='attendance_home'),
    path('attendance/group/<int:group_id>/open/', views.open_session, name='open_session'),
    path('attendance/session/<int:pk>/', views.session_detail, name='session_detail'),
    path('attendance/session/<int:pk>/scan/', views.scan, name='attendance_scan'),
    path('attendance/session/<int:pk>/mark/<int:student_id>/', views.mark, name='attendance_mark'),
    path('attendance/session/<int:pk>/close/', views.close_session, name='close_session'),

    # الطلاب
    path('students/', views_students.students_list, name='students_list'),
    path('students/add/', views_students.student_edit, name='student_add'),
    path('students/<int:pk>/', views_students.student_detail, name='student_detail'),
    path('students/<int:pk>/edit/', views_students.student_edit, name='student_edit'),
    path('students/import/', views_students.students_import, name='students_import'),
    path('students/import/upload/', views_students.students_import_upload, name='students_import_upload'),
    path('students/import/template/', views_students.students_import_template, name='students_import_template'),
    path('students/cards/', views_students.student_cards, name='student_cards'),
    path('students/cards/pdf/', views_students.student_cards_pdf, name='student_cards_pdf'),

    # الأقساط
    path('payments/', views_payments.payments_home, name='payments_home'),
    path('payments/mark/', views_payments.payment_mark, name='payment_mark'),
    path('payments/remind/', views_payments.payment_remind, name='payment_remind'),

    # التقارير
    path('reports/', views_reports.reports_home, name='reports_home'),
    path('reports/attendance/', views_reports.report_attendance, name='report_attendance'),
    path('reports/attendance/export/', views_reports.export_attendance_excel, name='export_attendance_excel'),
    path('reports/payments/', views_reports.report_payments, name='report_payments'),
    path('reports/payments/export/', views_reports.export_payments_excel, name='export_payments_excel'),

    # الامتحانات
    path('exams/', views_exams.exams_list, name='exams_list'),
    path('exams/create/', views_exams.exam_create, name='exam_create'),
    path('exams/<int:pk>/', views_exams.exam_detail, name='exam_detail'),
    path('exams/<int:pk>/score/', views_exams.exam_save_score, name='exam_save_score'),
    path('exams/<int:pk>/send/', views_exams.exam_send_results, name='exam_send_results'),

    # المدرسين والمجموعات (لوحة العميل)
    path('teachers/', views_setup.teachers_list, name='teachers_list'),
    path('teachers/add/', views_setup.teacher_edit, name='teacher_add'),
    path('teachers/<int:pk>/edit/', views_setup.teacher_edit, name='teacher_edit'),
    path('teachers/<int:pk>/toggle/', views_setup.teacher_toggle, name='teacher_toggle'),
    path('groups/', views_setup.groups_list, name='groups_list'),
    path('groups/add/', views_setup.group_edit, name='group_add'),
    path('groups/<int:pk>/edit/', views_setup.group_edit, name='group_edit'),
    path('groups/<int:pk>/toggle/', views_setup.group_toggle, name='group_toggle'),
]
