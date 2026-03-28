from datetime import datetime, timedelta

try:
    from apscheduler.schedulers.background import BackgroundScheduler
except ImportError:
    BackgroundScheduler = None


# =========================================================
# REMINDER SCHEDULER (исправлен)
# =========================================================
class ReminderScheduler:
    def __init__(self, callback):
        self.callback = callback
        self.scheduler = BackgroundScheduler() if BackgroundScheduler else None
        self._stopped = False
        if self.scheduler:
            self.scheduler.start()

    def add(self, seconds: int, text: str):
        if not self.scheduler or self._stopped:
            return
        self.scheduler.add_job(lambda: self.callback(text), 'date', run_date=datetime.now() + timedelta(seconds=seconds))

    def list_reminders(self):
        if not self.scheduler or self._stopped:
            return []
        return [(job.id, job.next_run_time) for job in self.scheduler.get_jobs()]

    def cancel_all(self):
        if self.scheduler and not self._stopped:
            self.scheduler.remove_all_jobs()

    def stop(self):
        if not self._stopped and self.scheduler and self.scheduler.running:
            self.scheduler.shutdown()
            self._stopped = True


__all__ = ["ReminderScheduler"]
