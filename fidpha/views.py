from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.views import PasswordResetView, PasswordResetConfirmView
from django.urls import reverse_lazy
from django.contrib.auth.models import User
from .models import UserProfile
import secrets
from django.utils import timezone
from django.core.mail import send_mail

from django.conf import settings


def custom_login(request):
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect("/admin/")
        return redirect("/portal/dashboard/")

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            if not user.is_staff:
                try:
                    account = user.profile.account
                    if not account.pharmacy_portal:
                        request.session["login_error"] = "Your account does not have portal access."
                        return redirect("/portal/login/")
                except:
                    request.session["login_error"] = "Your account is not linked to any pharmacy."
                    return redirect("/portal/login/")

            login(request, user)

            if user.is_staff:
                return redirect("/admin/")
            else:
                return redirect("/portal/dashboard/")
        else:
            request.session["login_error"] = "Invalid username or password."
            return redirect("/portal/login/")

    error = request.session.pop("login_error", None)
    if error:
        messages.error(request, error)

    return render(request, "fidpha/login.html")


def custom_logout(request):
    logout(request)
    messages.success(request, "You have been successfully signed out.")
    return redirect("/portal/login/")


def admin_welcome(request):
    welcome = request.session.pop("welcome_message", None)
    if welcome:
        messages.success(request, welcome)
    return redirect("/admin/")


@login_required(login_url="/portal/login/")
def setup_profile(request):
    if request.user.is_staff:
        return redirect("/admin/")

    try:
        profile = request.user.profile
    except:
        return redirect("/portal/login/")

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        password = request.POST.get("password", "").strip()

        # update name
        request.user.first_name = first_name
        request.user.last_name = last_name

        if email:
            # check email not already used
            if User.objects.filter(email=email).exclude(pk=request.user.pk).exists():
                messages.error(request, "This email is already used by another account.")
                return redirect("/portal/setup-profile/")

            # send verification email
            token = secrets.token_urlsafe(32)
            profile.verification_token = token
            profile.token_created_at = timezone.now()
            profile.save()

            verify_url = f"{request.scheme}://{request.get_host()}/portal/verify-email/{token}/"
            try:
                send_mail(
                    "FIDPHA — Verify your email",
                    f"Click the link to verify your email: {verify_url}",
                    settings.DEFAULT_FROM_EMAIL,
                    [email],
                    fail_silently=False,
                )
                request.user.email = email
                request.user.save()
                messages.success(request, "Verification email sent!")
                return redirect("/portal/verify-pending/")
            except Exception as e:
                messages.error(request, f"Failed to send email: {str(e)}")
                return redirect("/portal/setup-profile/")

        if password:
            request.user.set_password(password)
            request.user.save()
            login(request, request.user, backend='django.contrib.auth.backends.ModelBackend')
        else:
            request.user.save()

        return redirect("/portal/dashboard/")

    return render(request, "fidpha/setup_profile.html")



@login_required(login_url="/portal/login/")
def portal_profile(request):
    if request.user.is_staff:
        return redirect("/admin/")

    try:
        profile = request.user.profile
    except:
        return redirect("/portal/login/")

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        first_name = request.POST.get("first_name", "")
        last_name = request.POST.get("last_name", "")

        # only validate and process email if one was provided
        if email:
            if User.objects.filter(email=email).exclude(pk=request.user.pk).exists():
                messages.error(request, "This email is already used by another account.")
                return redirect("/portal/profile/")

            if email != request.user.email:
                profile.email_verified = False
                token = secrets.token_urlsafe(32)
                profile.verification_token = token
                profile.token_created_at = timezone.now()
                profile.save()

                from allauth.socialaccount.models import SocialAccount
                SocialAccount.objects.filter(user=request.user).delete()

                verify_url = f"{request.scheme}://{request.get_host()}/portal/verify-email/{token}/"
                try:
                    send_mail(
                        "FIDPHA — Verify your new email",
                        f"Click the link to verify your new email: {verify_url}",
                        settings.DEFAULT_FROM_EMAIL,
                        [email],
                        fail_silently=False,
                    )
                    messages.success(request, "Verification email sent to your new address!")
                except Exception as e:
                    messages.error(request, f"Failed to send email: {str(e)}")
                    return redirect("/portal/profile/")

            request.user.email = email

        request.user.first_name = first_name
        request.user.last_name = last_name
        request.user.save()

        if not email:
            messages.success(request, "Profile updated successfully!")

        return redirect("/portal/profile/")

    return render(request, "fidpha/profile.html", {
        "profile": profile,
    })




@login_required(login_url="/portal/login/")
def portal_profile_password(request):
    if request.user.is_staff:
        return redirect("/admin/")

    if request.method == "POST":
        current_password = request.POST.get("current_password")
        new_password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        # verify current password
        if not request.user.check_password(current_password):
            messages.error(request, "Current password is incorrect.")
            return redirect("/portal/profile/")

        # check new passwords match
        if new_password != confirm_password:
            messages.error(request, "New passwords don't match.")
            return redirect("/portal/profile/")

        # validate strength
        if len(new_password) < 8:
            messages.error(request, "Password must be at least 8 characters.")
            return redirect("/portal/profile/")
        if new_password.isdigit():
            messages.error(request, "Password can't be entirely numeric.")
            return redirect("/portal/profile/")
        if not any(c.isupper() for c in new_password):
            messages.error(request, "Password must contain at least one uppercase letter.")
            return redirect("/portal/profile/")
        if not any(c.isdigit() for c in new_password):
            messages.error(request, "Password must contain at least one number.")
            return redirect("/portal/profile/")
        if not any(c in "!@#$%^&*()_+-=[]{}|;':\",./<>?" for c in new_password):
            messages.error(request, "Password must contain at least one special character.")
            return redirect("/portal/profile/")

        request.user.set_password(new_password)
        request.user.save()
        login(request, request.user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(request, "Password updated successfully!")
        return redirect("/portal/profile/")

    return redirect("/portal/profile/")



@login_required(login_url="/portal/login/")
def verify_pending(request):
    if request.user.is_staff:
        return redirect("/admin/")

    try:
        profile = request.user.profile
    except:
        return redirect("/portal/login/")

    if profile.email_verified:
        return redirect("/portal/dashboard/")

    if not request.user.email:
        return render(request, "fidpha/verify_pending.html", {"no_email": True})

    # always generate a fresh token and resend
    token = secrets.token_urlsafe(32)
    profile.verification_token = token
    profile.token_created_at = timezone.now()
    profile.save()

    verify_url = f"{request.scheme}://{request.get_host()}/portal/verify-email/{token}/"
    try:
        send_mail(
            "FIDPHA — Verify your email",
            f"Click the link to verify your email: {verify_url}",
            settings.DEFAULT_FROM_EMAIL,
            [request.user.email],
            fail_silently=False,
        )
    except Exception as e:
        messages.error(request, f"Failed to send email: {str(e)}")
        return redirect("/portal/dashboard/")

    return render(request, "fidpha/verify_pending.html", {"no_email": False})




def verify_email(request, token):
    try:
        profile = UserProfile.objects.get(verification_token=token)
    except UserProfile.DoesNotExist:
        messages.error(request, "Invalid verification link.")
        return redirect("/portal/login/")

    if timezone.now() - profile.token_created_at > timezone.timedelta(hours=24):
        messages.error(request, "Verification link has expired. Please request a new one.")
        return redirect("/portal/setup-profile/")

    profile.email_verified = True
    profile.verification_token = None
    profile.token_created_at = None
    profile.save()

    messages.success(request, "Email verified successfully! You can now log in.")
    return redirect("/portal/login/")


@login_required(login_url="/portal/login/")
def portal_dashboard(request):
    if request.user.is_staff:
        return redirect("/admin/")

    try:
        profile = request.user.profile
    except:
        return redirect("/portal/login/")

    account = profile.account
    contracts = account.contracts.all().order_by("-start_date")
    active_contracts = contracts.filter(status="active")

    # calculate remaining days for active contract
    from django.utils import timezone
    active_contract_days_remaining = None
    if active_contracts.exists():
        active_contract = active_contracts.first()
        delta = active_contract.end_date - timezone.now()
        active_contract_days_remaining = delta.days

    return render(request, "fidpha/dashboard.html", {
        "account": account,
        "contracts": contracts,
        "active_contracts": active_contracts,
        "email_verified": profile.email_verified,
        "active_contract_days_remaining": active_contract_days_remaining,
    })


@login_required(login_url="/portal/login/")
def portal_contracts(request):
    if request.user.is_staff:
        return redirect("/admin/")

    try:
        profile = request.user.profile
    except:
        return redirect("/portal/login/")

    all_contracts = profile.account.contracts.all().order_by("-start_date")
    active_contracts = all_contracts.filter(status="active")
    inactive_contracts = all_contracts.filter(status="inactive")

    return render(request, "fidpha/contracts.html", {
        "active_contracts": active_contracts,
        "inactive_contracts": inactive_contracts,
        "profile": profile,
    })




# -----------------------
# Password Reset
# -----------------------

class CustomPasswordResetForm(PasswordResetForm):
    def clean_email(self):
        email = self.cleaned_data.get("email")
        if not User.objects.filter(email=email).exists():
            raise ValidationError("No account found with this email address.")
        return email


class CustomPasswordResetView(PasswordResetView):
    form_class = CustomPasswordResetForm
    template_name = "registration/password_reset_form.html"
    success_url = reverse_lazy("password_reset_done")

    def form_invalid(self, form):
        self.request.session["reset_errors"] = True
        return redirect("/accounts/password_reset/")

    def get(self, request, *args, **kwargs):
        errors = request.session.pop("reset_errors", None)
        form = self.form_class()
        return render(request, self.template_name, {
            "form": form,
            "session_errors": errors,
        })

# -----------------------
# Password Reset Confirm
# -----------------------

class CustomSetPasswordForm(SetPasswordForm):
    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("new_password1")
        password2 = cleaned_data.get("new_password2")

        if password1 and password2:
            if password1 != password2:
                raise ValidationError("The two passwords don't match.")
            if len(password1) < 8:
                raise ValidationError("Password must be at least 8 characters.")
            if password1.isdigit():
                raise ValidationError("Password can't be entirely numeric.")
            if not any(c.isupper() for c in password1):
                raise ValidationError("Password must contain at least one uppercase letter.")
            if not any(c.isdigit() for c in password1):
                raise ValidationError("Password must contain at least one number.")
            if not any(c in "!@#$%^&*()_+-=[]{}|;':\",./<>?" for c in password1):
                raise ValidationError("Password must contain at least one special character.")
        return cleaned_data


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    form_class = CustomSetPasswordForm
    template_name = "registration/password_reset_confirm.html"
    success_url = reverse_lazy("password_reset_complete")

    def form_invalid(self, form):
        errors = []
        for field_errors in form.errors.values():
            errors.extend(field_errors)
        self.request.session["confirm_errors"] = errors
        return redirect(self.request.path)

    def get(self, request, *args, **kwargs):
        errors = request.session.pop("confirm_errors", None)
        response = super().get(request, *args, **kwargs)
        response.context_data["session_errors"] = errors
        return response