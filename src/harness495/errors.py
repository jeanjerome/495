"""Erreurs observables produites par le parcours applicatif."""


class ChangeError(RuntimeError):
    """Le parcours ne peut pas produire un résultat vérifié."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
