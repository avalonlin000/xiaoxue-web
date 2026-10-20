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
            if target.endswith(".manifest"):
                module_id = target.split(".")[-2]
                return types.SimpleNamespace(MODULE=_manifest(module_id))
            if ".broken." in target:
                raise ImportError("synthetic failure")
            return types.SimpleNamespace(router=healthy_router)

        status = attach_feature_routers(app, modules=("broken", "healthy"), loader=loader)

        self.assertEqual(status["broken"]["status"], "broken")
        self.assertEqual(status["healthy"]["status"], "healthy")
        with TestClient(app) as client:
            self.assertEqual(client.get("/healthy").json(), {"ok": True})

    def test_invalid_manifest_does_not_block_other_capabilities(self):
        app = FastAPI()
        healthy_router = APIRouter()

        def loader(target: str):
            module_id = target.split(".")[-2]
            if target.endswith(".manifest"):
                if module_id == "broken":
                    return types.SimpleNamespace(MODULE={"id": "broken", "name": "broken"})
                return types.SimpleNamespace(MODULE=_manifest(module_id))
            return types.SimpleNamespace(router=healthy_router)

        status = attach_feature_routers(app, modules=("broken", "healthy"), loader=loader)

        self.assertEqual(status["broken"]["reason_code"], "invalid_module_manifest")
        self.assertEqual(status["healthy"]["status"], "healthy")


def _manifest(module_id: str) -> dict:
    return {
        "id": module_id,
        "name": module_id,
        "version": "1.0.0",
        "purpose": "test capability",
        "examples": [],
        "inputs": {},
        "effect": "read",
        "reads": [],
        "writes": [],
        "output_schema": {},
        "source_policy": {},
        "settings": {},
        "dependencies": [],
        "health": {},
        "tests": [],
    }


if __name__ == "__main__":
    unittest.main()
