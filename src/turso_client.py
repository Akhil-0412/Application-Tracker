import requests

class TursoCursor:
    def __init__(self, data):
        self.data = data
        self.lastrowid = data.get("last_insert_rowid")
        
    def fetchall(self):
        cols = [c["name"] for c in self.data.get("cols", [])]
        res = []
        for row in self.data.get("rows", []):
            parsed_row = []
            for col_obj in row:
                if col_obj["type"] == "null":
                    parsed_row.append(None)
                elif col_obj["type"] == "integer":
                    parsed_row.append(int(col_obj["value"]))
                elif col_obj["type"] == "float":
                    parsed_row.append(float(col_obj["value"]))
                else:
                    parsed_row.append(col_obj["value"])
            res.append(dict(zip(cols, parsed_row)))
        return res

    def fetchone(self):
        rows = self.fetchall()
        return rows[0] if rows else None

class TursoConnection:
    def __init__(self, url: str, auth_token: str):
        if url.startswith("libsql://"):
            url = url.replace("libsql://", "https://")
        
        # Clean up any accidental copy-paste newlines or quotes from environment variables
        self.url = url.strip().strip('"').strip("'").rstrip("/") + "/v2/pipeline"
        self.token = auth_token.strip().strip('"').strip("'")

    def execute(self, query: str, params=None):
        args = []
        if params:
            for p in params:
                if p is None:
                    args.append({"type": "null"})
                elif isinstance(p, int):
                    args.append({"type": "integer", "value": str(p)})
                elif isinstance(p, float):
                    args.append({"type": "float", "value": p})
                else:
                    args.append({"type": "text", "value": str(p)})
                    
        data = {
            "requests": [
                {"type": "execute", "stmt": {"sql": query, "args": args}},
                {"type": "close"}
            ]
        }
        res = requests.post(
            self.url,
            headers={"Authorization": f"Bearer {self.token}"},
            json=data
        )
        if res.status_code != 200:
            raise Exception(f"Turso Error: {res.text}")
            
        result = res.json()["results"][0]["response"]["result"]
        return TursoCursor(result)

    def commit(self):
        # HTTP API Auto-commits on execute for non-transaction queries
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
