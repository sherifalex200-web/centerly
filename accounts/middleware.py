from django.shortcuts import redirect
from django.urls import reverse


class CenterMiddleware:
    """
    - يحط request.center عشان كل View يستخدمه
    - يمنع المستخدم اللي اشتراك سنتره انتهى
    """
    EXEMPT_PREFIXES = ('/admin/', '/login/', '/logout/', '/static/', '/media/', '/billing/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.center = None
        user = request.user
        if user.is_authenticated and not request.path.startswith(self.EXEMPT_PREFIXES):
            if user.is_superuser and not user.center:
                return redirect('/admin/')
            if not user.center:
                return redirect('/login/')
            request.center = user.center
            if not user.center.subscription_active:
                return redirect(reverse('billing_expired'))
        return self.get_response(request)