import os, httpx
class DifyError(Exception): pass
class DifyWorkflowAdapter:
    def __init__(self):
        self.base = os.getenv("DIFY_BASE_URL", "").rstrip("/")
        self.key = os.getenv("DIFY_WORKFLOW_API_KEY", "").strip()
        self.user = os.getenv("DIFY_USER_LABEL", "aiops-local")
    @property
    def configured(self): return bool(self.base and self.key)
    async def run(self, inputs):
        if not self.configured: raise DifyError("DIFY_BASE_URL 또는 DIFY_WORKFLOW_API_KEY 미설정")
        try:
            async with httpx.AsyncClient(timeout=180, follow_redirects=False) as client:
                r = await client.post(f"{self.base}/v1/workflows/run",headers={"Authorization":f"Bearer {self.key}"},json={"inputs":inputs,"response_mode":"blocking","user":self.user})
                r.raise_for_status(); return r.json()
        except Exception as exc: raise DifyError(f"Dify Workflow 호출 실패({type(exc).__name__})") from exc
