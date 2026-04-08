from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from django.contrib.auth.models import User
from allauth.exceptions import ImmediateHttpResponse
from django.shortcuts import redirect
from django.contrib import messages


class FIDPHAAccountAdapter(DefaultAccountAdapter):
    def add_message(self, request, level, message_template, message_context=None, extra_tags=""):
        pass  # suppress all allauth automatic messages


class FIDPHASocialAccountAdapter(DefaultSocialAccountAdapter):

    def pre_social_login(self, request, sociallogin):
        email = sociallogin.account.extra_data.get("email")
        if not email:
            messages.error(request, "No email provided by Google.")
            raise ImmediateHttpResponse(redirect("/portal/login/"))

        try:
            user = User.objects.get(email=email)
            sociallogin.connect(request, user)

            # check portal access for non-staff users
            if not user.is_staff:
                try:
                    account = user.profile.account
                    if not account.pharmacy_portal:
                        messages.error(request, "Your account does not have portal access.")
                        raise ImmediateHttpResponse(redirect("/portal/login/"))
                except ImmediateHttpResponse:
                    raise
                except Exception:
                    messages.error(request, "Your account is not linked to any pharmacy.")
                    raise ImmediateHttpResponse(redirect("/portal/login/"))

        except ImmediateHttpResponse:
            raise
        except User.DoesNotExist:
            messages.error(request, "No account found with this Google email. Please contact your administrator.")
            raise ImmediateHttpResponse(redirect("/portal/login/"))

    def get_login_redirect_url(self, request):
        user = request.user
        name = user.get_full_name() or user.username
        request.session["welcome_message"] = f"Welcome back, {name}!"
        if user.is_staff:
            return "/admin/welcome/"
        return "/portal/dashboard/"