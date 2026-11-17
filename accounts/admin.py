# accounts/admin.py
from django.contrib import admin
from .models import Center, User

@admin.register(Center)
class CenterAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'plan', 'subscription_end', 'is_active', 'messages_used')

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('phone', 'name', 'center', 'role', 'is_active')
    def save_model(self, request, obj, form, change):
        if 'password' in form.changed_data:
            obj.set_password(obj.password)
        super().save_model(request, obj, form, change)