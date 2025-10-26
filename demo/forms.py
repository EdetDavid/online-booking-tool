from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, Admin, Staff, Profile, ThriveAdmin




class ThriveAdminUserCreationForm(UserCreationForm):
    first_name = forms.CharField(max_length=100, required=True)
    last_name = forms.CharField(max_length=100, required=True)
    email = forms.EmailField(required=True)
    # Phone is part of the Admin model, not User
    phone = forms.CharField(max_length=15, required=False)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name',
                  'email', 'phone',  'password1', 'password2']

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            # Create Admin profile with phone number
            ThriveAdmin.objects.create(
                admin=user,
                first_name=self.cleaned_data['first_name'],
                last_name=self.cleaned_data['last_name'],
                # Storing phone in Admin model
                phone=self.cleaned_data['phone'],
            )
        return user


class AdminUserCreationForm(UserCreationForm):
    first_name = forms.CharField(max_length=100, required=True)
    last_name = forms.CharField(max_length=100, required=True)
    email = forms.EmailField(required=True)
    # Phone is part of the Admin model, not User
    phone = forms.CharField(max_length=15, required=False)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name',
                  'email', 'phone',  'password1', 'password2']

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            # Create Admin profile with phone number
            Admin.objects.create(
                admin=user,
                first_name=self.cleaned_data['first_name'],
                last_name=self.cleaned_data['last_name'],
                # Storing phone in Admin model
                phone=self.cleaned_data['phone'],
            )
        return user


class StaffUserCreationForm(UserCreationForm):
    first_name = forms.CharField(max_length=100, required=True)
    last_name = forms.CharField(max_length=100, required=True)
    email = forms.EmailField(required=True)
    # Phone is part of the Staff model, not User
    phone = forms.CharField(max_length=15, required=False)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name',
                  'email', 'phone', 'password1', 'password2']

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            # Create Staff profile with phone number
            Staff.objects.create(
                staff=user,
                first_name=self.cleaned_data['first_name'],
                last_name=self.cleaned_data['last_name'],
                # Storing phone in Staff model
                phone=self.cleaned_data['phone'],
            )
        return user


class ProfileForm(forms.ModelForm):

    class Meta:
        model = Profile
        fields = ['profile_picture']
