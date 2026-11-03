from django.db import models


class User(models.Model):
    """
    A basic user model that could be extended based on application needs.
    For now, using a simple model instead of extending AbstractUser to avoid
    complications with Django's default User model.
    """
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.email