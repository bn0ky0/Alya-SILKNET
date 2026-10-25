import uuid

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from silknet.single_instance import SingleInstanceGuard


def test_second_instance_asks_the_first_one_to_activate() -> None:
    app = QApplication.instance() or QApplication([])
    name = f"Alya.SILKNET.Test.{uuid.uuid4().hex}"
    first = SingleInstanceGuard(name)
    second = SingleInstanceGuard(name)
    activations: list[bool] = []
    try:
        assert first.try_acquire()
        first.activation_requested.connect(lambda: activations.append(True))

        assert not second.try_acquire()
        QTest.qWait(250)

        assert activations == [True]
    finally:
        second.close()
        first.close()
    app.quit()
