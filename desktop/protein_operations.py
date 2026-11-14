"""Protein-page operation envelopes; other Desktop Worker contracts are unchanged."""
from threading import Lock

from PySide6.QtCore import QObject,Signal,Slot

from desktop.workers import Worker,sanitize_error


class OperationSignals(QObject):
    settled=Signal(object)


class OperationWorker(Worker):
    """Always report physical completion, including suppressed/cancelled work.

    Cancellation also reports immediately so a cleared queued QRunnable does not
    leave a logical task busy forever. Running callables are never force-killed.
    """
    def __init__(self,function,operation_id):
        super().__init__(function)
        self.signals=OperationSignals()
        self.operation_id=operation_id
        self._state_lock=Lock()
        self._started=False
        self._physically_done=False

    def cancel(self):
        with self._state_lock:
            if self._physically_done:return
            self._cancelled.set()
            started=self._started
            if not started:self._physically_done=True
        self.signals.settled.emit(dict(operation_id=self.operation_id,
            phase='CANCEL_REQUESTED' if started else 'COMPLETED',status='CANCELLED',executed=started))
        if not started:
            with self._lock:self._instances.discard(self)

    @Slot()
    def run(self):
        with self._state_lock:
            if self._physically_done:return
            self._started=True
        outcome=dict(operation_id=self.operation_id,phase='COMPLETED',executed=True,status='FAILED',error='OPERATION_ABORTED')
        try:
            if self._cancelled.is_set():outcome['status']='CANCELLED'
            else:
                outcome['value']=self.function(*self.args,**self.kwargs)
                outcome['status']='CANCELLED' if self._cancelled.is_set() else 'SUCCEEDED'
        except BaseException as exc:
            outcome.update(status='CANCELLED' if self._cancelled.is_set() else 'FAILED',
                error=sanitize_error(str(exc),self.secrets))
        finally:
            with self._state_lock:self._physically_done=True
            with self._lock:self._instances.discard(self)
            self.signals.settled.emit(outcome)
