from django.apps import AppConfig


class AgentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'agents'
    verbose_name = '智能代理'
    
    def ready(self):
        """应用启动时的初始化"""
        pass