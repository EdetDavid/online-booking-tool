from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import UserCreationForm
from .models import User, Admin, Staff, Profile, TravelAgency, Organization


def normalize_company_code(value):
    return "".join(str(value or "").split()).upper()


def unique_organization_join_code(name):
    return Organization.unique_join_code(name)


def style_auth_form_fields(form):
    autocomplete = {
        'username': 'username',
        'email': 'email',
        'first_name': 'given-name',
        'last_name': 'family-name',
        'phone': 'tel',
        'password': 'current-password',
        'password1': 'new-password',
        'password2': 'new-password',
        'company_code': 'organization',
        'organization_code': 'organization',
        'organization_name': 'organization',
    }

    for name, field in form.fields.items():
        field.label = field.label or name.replace('_', ' ').capitalize()
        widget = field.widget
        existing_class = widget.attrs.get('class', '')
        widget.attrs['class'] = f"{existing_class} auth-input".strip()
        if not widget.attrs.get('placeholder') or widget.attrs.get('placeholder') == 'None':
            widget.attrs['placeholder'] = field.label
        if name in autocomplete:
            widget.attrs.setdefault('autocomplete', autocomplete[name])

        if name == 'phone':
            widget.attrs.setdefault('inputmode', 'tel')
        elif name in {'company_code', 'organization_code', 'approval_code'}:
            widget.attrs.setdefault('autocapitalize', 'characters')
            widget.attrs.setdefault('spellcheck', 'false')


class StandardAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_auth_form_fields(self)


class TravelAgencyAuthenticationForm(StandardAuthenticationForm):
    company_code = forms.CharField(
        label="Company Code",
        max_length=50,
        required=True,
        help_text="Enter your Travel Agency company code.",
    )

    def clean_company_code(self):
        return normalize_company_code(self.cleaned_data.get('company_code'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(['username', 'company_code', 'password'])
        style_auth_form_fields(self)


class TravelAgencyUserCreationForm(UserCreationForm):
    first_name = forms.CharField(max_length=100, required=True)
    last_name = forms.CharField(max_length=100, required=True)
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=15, required=False)
    approval_code = forms.CharField(
        label="Approval Code",
        max_length=50,
        required=False,
        help_text="Use the default code or an approved Travel Agency company code.",
    )
    company_code = forms.CharField(
        label="Your Company Code",
        max_length=50,
        required=False,
        help_text="Optional code other Travel Agencies can use for approval.",
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name',
                  'email', 'phone', 'approval_code', 'company_code', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_auth_form_fields(self)

    @staticmethod
    def normalize_code(value):
        return normalize_company_code(value)

    def clean_approval_code(self):
        return self.normalize_code(self.cleaned_data.get('approval_code'))

    def clean_company_code(self):
        company_code = self.normalize_code(self.cleaned_data.get('company_code'))
        if company_code and TravelAgency.objects.filter(company_code=company_code).exists():
            raise forms.ValidationError("This company code is already in use.")
        return company_code

    def approval_code_is_valid(self):
        approval_code = self.cleaned_data.get('approval_code')
        if not approval_code:
            return False

        default_code = self.normalize_code(
            getattr(settings, 'TRAVEL_AGENCY_DEFAULT_COMPANY_CODE', 'OBT1234')
        )
        if approval_code == default_code:
            return True

        return TravelAgency.objects.filter(
            company_code=approval_code,
            approval_status=True,
        ).exists()

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            TravelAgency.objects.create(
                admin=user,
                first_name=self.cleaned_data['first_name'],
                last_name=self.cleaned_data['last_name'],
                phone=self.cleaned_data['phone'],
                company_code=self.cleaned_data.get('company_code') or None,
                approval_status=self.approval_code_is_valid(),
            )
        return user


class AdminUserCreationForm(UserCreationForm):
    first_name = forms.CharField(max_length=100, required=True)
    last_name = forms.CharField(max_length=100, required=True)
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=15, required=False)
    organization_name = forms.CharField(
        label="Organization",
        max_length=200,
        required=False,
        help_text="Company or organization this admin manages.",
    )
    organization_code = forms.CharField(
        label="Organization Code",
        max_length=50,
        required=False,
        help_text="Use the code from your travel agency if your organization already exists.",
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name',
                  'email', 'phone', 'organization_name', 'organization_code', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_auth_form_fields(self)

    def clean_organization_code(self):
        return normalize_company_code(self.cleaned_data.get('organization_code'))

    def clean(self):
        cleaned_data = super().clean()
        organization_code = cleaned_data.get('organization_code')
        organization_name = " ".join(str(cleaned_data.get('organization_name') or "").split())

        if organization_code:
            organization = Organization.objects.filter(
                join_code=organization_code,
                active=True,
            ).first()
            if not organization:
                self.add_error('organization_code', "Enter a valid organization code.")
            cleaned_data['organization'] = organization
            return cleaned_data

        if not organization_name:
            self.add_error('organization_name', "Enter your organization or use an organization code.")
        else:
            cleaned_data['organization_name'] = organization_name

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            # Create Admin profile with phone number
            organization = self.cleaned_data.get('organization')
            if not organization:
                organization = Organization.get_or_create_by_name(
                    self.cleaned_data['organization_name']
                )
            Admin.objects.create(
                admin=user,
                organization=organization,
                first_name=self.cleaned_data['first_name'],
                last_name=self.cleaned_data['last_name'],
                phone=self.cleaned_data['phone'],
            )
        return user


class StaffUserCreationForm(UserCreationForm):
    first_name = forms.CharField(max_length=100, required=True)
    last_name = forms.CharField(max_length=100, required=True)
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=15, required=False)
    organization_code = forms.CharField(
        label="Organization Code",
        max_length=50,
        required=True,
        help_text="Enter the organization code provided by your travel agency or company admin.",
    )

    def clean_organization_code(self):
        organization_code = normalize_company_code(self.cleaned_data.get('organization_code'))
        organization = Organization.objects.filter(
            join_code=organization_code,
            active=True,
        ).first()
        if not organization:
            raise forms.ValidationError("Enter a valid organization code.")
        self.cleaned_data['organization'] = organization
        return organization_code

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name',
                  'email', 'phone', 'organization_code', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_auth_form_fields(self)

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            # Create Staff profile with phone number
            Staff.objects.create(
                staff=user,
                organization=self.cleaned_data['organization'],
                first_name=self.cleaned_data['first_name'],
                last_name=self.cleaned_data['last_name'],
                phone=self.cleaned_data['phone'],
            )
        return user


class ProfileForm(forms.ModelForm):

    class Meta:
        model = Profile
        fields = ['profile_picture']


class TravelAgencyOrganizationForm(forms.ModelForm):
    join_code = forms.CharField(
        label="Organization Code",
        max_length=50,
        required=False,
        help_text="Share this code with corporate admins and staff.",
    )

    class Meta:
        model = Organization
        fields = ['name', 'join_code']

    def clean_name(self):
        return " ".join(str(self.cleaned_data.get('name') or "").split())

    def clean_join_code(self):
        join_code = normalize_company_code(self.cleaned_data.get('join_code'))
        if not join_code:
            join_code = unique_organization_join_code(self.cleaned_data.get('name'))
        queryset = Organization.objects.filter(join_code=join_code)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("This organization code is already in use.")
        return join_code


class ExchangeRateForm(forms.ModelForm):
    class Meta:
        model = TravelAgency
        fields = ["exchange_rate"]
        labels = {
            "exchange_rate": "USD to NGN exchange rate",
        }
        help_texts = {
            "exchange_rate": "Enter the naira value of one US dollar.",
        }
        widgets = {
            "exchange_rate": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0.0001",
                    "step": "0.0001",
                    "inputmode": "decimal",
                }
            ),
        }
