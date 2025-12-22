from PyQt6.QtCore import QObject, QThreadPool, pyqtSignal, pyqtSlot
from src.workers.translate_worker import TranslateWorker

class TranslationService(QObject):
    _instance = None
    task_status_changed = pyqtSignal(str, str, str) # image_path, lang_code, status

    def __init__(self):
        super().__init__()
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(1) # Sequential execution
        self.tasks = {} # (image_path, lang_code) -> status string

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = TranslationService()
        return cls._instance

    def submit(self, worker: TranslateWorker):
        """Submit a translation worker to the queue."""
        key = (worker.image_path, worker.target_lang.value)
        self.update_status(worker.image_path, worker.target_lang.value, "queued")
        
        # Connect signals to maintain state
        worker.signals.started.connect(lambda lang: self.update_status(worker.image_path, lang, "translating"))
        # Updated to handle history argument (5th arg)
        worker.signals.finished.connect(lambda p, s, o, l, h: self.update_status(p, l, None))
        
        self.thread_pool.start(worker)

    def update_status(self, path: str, lang: str, status: str):
        key = (path, lang)
        if status is None:
            if key in self.tasks:
                del self.tasks[key]
        else:
            self.tasks[key] = status
        self.task_status_changed.emit(path, lang, status if status else "finished")

    def get_status(self, path: str, lang: str) -> str:
        """Returns 'queued', 'translating', or None."""
        return self.tasks.get((path, lang))

    def active_tasks(self) -> int:
        return self.thread_pool.activeThreadCount()
