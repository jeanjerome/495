"""Erreurs observables produites par le parcours applicatif."""


class ChangeError(RuntimeError):
    """Le parcours ne peut pas produire un résultat vérifié."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class ConfigurationError(ChangeError):
    """Le contrat existe et se lit, mais son format est invalide."""

    def __init__(self, message: str) -> None:
        super().__init__("configuration", message)
