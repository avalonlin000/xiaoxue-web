import types
import unittest

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from xiaoxue_api.core.module_loader import attach_feature_routers


class ModuleLoaderTests(unittest.TestCase):
    def test_one_import_failure_does_not_block_other_routers(self):
        app = FastAPI()
        healthy_router = APIRouter()

        @healthy_router.get("/healthy")
        def healthy():
            return {"ok": True}

        def loader(target: str):
            if ".broken." in target:
                raise ImportError("synthetic failure")
            return types.SimpleNamespace(router=healthy_router)

        status = attach_feature_routers(app, modules=("broken", "healthy"), loader=loader)

        self.assertEqual(status["broken"]["status"], "broken")
        self.assertEqual(status["healthy"]["status"], "healthy")
        with TestClient(app) as client:
            self.assertEqual(client.get("/healthy").json(), {"ok": True})


if __name__ == "__main__":
    unittest.main()
