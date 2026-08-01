import requests

from automation_errors import PublicAutomationError
from config import EVO_API_KEY, EVO_URL, INSTANCE


class EvolutionClient:
    def __init__(self):
        self.__api_key = EVO_API_KEY
        self.__base_url = EVO_URL
        self.__instance = INSTANCE
        if self.__base_url and not self.__base_url.startswith("https://"):
            raise PublicAutomationError("EVO_URL deve usar HTTPS.")
        self.__headers = {"Content-Type": "application/json", "apikey": self.__api_key}

    def notification(self, number: str, msg: str):
        payload = {"number": f"{number}", "text": msg, "delay": 5}
        response = requests.post(
            url=f"{self.__base_url}message/sendText/{self.__instance}",
            headers=self.__headers,
            json=payload,
            timeout=10,
            allow_redirects=False,
        )
        response.raise_for_status()
        return response
