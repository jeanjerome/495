# Rapport : configuration et vérification réutilisables

## Portée

Ce rapport clôt le premier incrément du
[plan global](../plan-global.md#1-rendre-la-configuration-et-la-vérification-réutilisables).
Il compare le comportement livré aux critères de fin de l’incrément et à sa
[conception](conception.md), énumère les contrôles réellement exécutés et
consigne les limites qui subsistent.

Il décrit un état constaté à sa rédaction. L’[état de
l’implémentation](../../implementation.md) reste l’autorité sur le comportement
disponible et doit primer en cas de divergence ultérieure.

## Comportements livrés

| Critère | Comportement livré | Où le constater |
| --- | --- | --- |
| une configuration peut être proposée, examinée, validée et enregistrée explicitement | `495 configure propose` restitue une proposition sans écriture ; `configure validate` contrôle un contrat présent ; `configure write` n’enregistre qu’une proposition relue et refuse d’écraser sans `--overwrite` | `configuration.py`, `tests/test_configuration.py`, `tests/test_cli.py` |
| un candidat existant peut être vérifié sans agent ni authentification | `495 verify` compare l’arbre de travail à une référence de la lignée de `HEAD` et exécute les contrôles avec un `CODEX_HOME` jetable ; `codex login status` n’est jamais appelé | `verification.verify_candidate`, `composition.verify_with_codex_sandbox` |
| le parcours avec agent réutilise le même moteur de vérification | `change.run_change` appelle `verification.validate_controls` puis `verification.run_checks`, les mêmes fonctions que `verify` | `change.py`, test de bout en bout consigné dans l’état de l’implémentation |
| les contrôles restent sandboxés et ne modifient pas silencieusement le candidat | chaque contrôle passe par `codex sandbox` avec le profil déclaré et le réseau désactivé ; le candidat est observé après chaque contrôle et une différence de digest interrompt la suite avec une violation | `controls.CodexSandboxControlRunner`, `verification.run_checks` |
| les sorties capturées sont bornées et leur troncature observable | `process.execute_process` conserve 4 194 304 octets par flux, vide le reste et rapporte `stdout_bytes`, `stderr_bytes`, `stdout_truncated`, `stderr_truncated` ; `output_limit_bytes` figure dans chaque document ; un flux JSONL tronqué produit `agent_failed` | `process.py`, `tests/test_process.py` |
| l’ancienne invocation conserve son comportement | un premier argument commençant par `--` est traité comme `change` ; `tools/run_change.py` délègue à la même CLI | `cli.normalize_arguments`, test de compatibilité |
| codes de sortie et formats JSON cohérents | table unique `EXIT_CODES` dérivée de l’issue ; un seul document indenté à clés triées par commande ; `runner` et `output_limit_bytes` présents dans `verify`, `change` et les trois opérations de `configure` | `cli.py`, tests de forme des documents |
| README décrit l’usage courant | sections « Vérifier un candidat déjà présent », « Configurer un dépôt » et « Résultat et codes de sortie » | `README.md` |
| l’état de l’implémentation ne décrit que les comportements disponibles | chaque champ documenté est produit par le code et couvert par un test | `docs/implementation.md` |
| le plan global reste prospectif | son point de départ est daté explicitement et renvoie à l’état de l’implémentation pour l’état courant | `docs/chantiers/plan-global.md` |

Le critère de fin du plan, un projet indépendant de Python qui enregistre sa
configuration, modifie un fichier et obtient une vérification sans
authentification, est observé sur un dépôt shell : les essais réels consignés
dans l’état de l’implémentation montrent le même digest de candidat, le même
verdict et un bloc `checks` identique à la durée près entre `change` et
`verify`.

## Écarts entre la conception et l’implémentation

Ces choix ont été pris pendant l’implémentation ; la conception les intègre
lorsqu’ils modifient une décision.

- **Timeout non attesté.** L’essai réel de `configure propose` a montré que
  l’agent répondait `blocked` faute de délai attesté par le dépôt. Le prompt
  demande depuis `null`, le contrat accepte `null` comme absence de borne de
  durée, et l’option `--timeout-seconds` complète ces contrôles sur demande.
  `limitations` nomme les contrôles concernés et l’origine de leur timeout.
- **Timeout restitué par contrôle.** Chaque bloc de `checks` porte
  `timeout_seconds`, afin qu’un lecteur distingue un contrôle borné d’un
  contrôle sans limite de durée.
- **Nom du runner.** `runner.name` vaut `codex-sandbox` par construction dans
  l’application, car seule cette adaptation de `ControlRunner` existe ; la
  version vient de `codex --version`. Un second runtime devra porter son nom
  lui-même.
- **Ordre des préconditions dans `verify`.** La version du runner est lue avant
  la résolution des exécutables et la sonde des profils, de sorte que `runner`
  soit connu dès qu’un document complet est produit.

## Contrôles exécutés

| Contrôle | Résultat |
| --- | --- |
| `uv run python -B -m unittest discover -s tests -p 'test_*.py'` | 119 tests, OK |
| `uv run python tools/run_bootstrap.py validate` | configuration valide, 41 fichiers, 1 contrôle |
| `uv run python tools/run_bootstrap.py run` | PASS |
| `git diff --check` | aucun avertissement |

Les tests couvrent, avec le double déterministe de Codex : les issues de
`verify`, `configure` et `change`, la compatibilité de l’invocation
historique, la borne des deux flux émis simultanément, le timeout avec sortie
volumineuse, la coupure d’une séquence UTF-8 à la borne, un contrôle bavard
dont le verdict est conservé et un flux JSONL tronqué rapporté comme
`agent_failed`.

## Essais réels

Tous les essais ont été menés sur macOS avec Codex CLI `0.153.3`.

- **Sans authentification.** `configure validate` puis `verify` sur un dépôt
  shell temporaire avec un `CODEX_HOME` vide et le réseau du sandbox désactivé.
  Le contrôle émet 4 300 001 octets : `no_candidate` sur l’arbre propre,
  `candidate_failed` puis `candidate_verified` après modification, avec
  `stdout_bytes` à 4 300 001, `stdout_truncated` vrai et un texte conservé de
  4 194 304 caractères. Le dépôt est resté intact. Aucun service externe n’a
  été contacté.
- **Avec Codex authentifié.** `configure propose`, `configure write`, `verify`
  puis `change` sur un dépôt shell doté d’un `Makefile`, consignés dans l’état
  de l’implémentation. Ces essais précèdent l’ajout des bornes de sortie : le
  parcours `change` n’a pas été rejoué depuis, et ses champs de troncature sont
  couverts par les tests seulement.

## Limites restantes

- Seul `codex sandbox` exécute les contrôles ; `codex` doit être installé même
  sans authentification, et son confinement n’est éprouvé que sur macOS.
- La référence de `verify` doit appartenir à la lignée de `HEAD`.
- La troncature conserve un préfixe, jamais la fin d’une sortie, et la borne
  n’est pas configurable.
- Un contrôle dont `timeout_seconds` vaut `null` n’est pas borné en durée.
- Un processus qui échappe au groupe de son contrôle et garde un tube ouvert
  retarde la fin de la capture jusqu’à la fermeture de ce tube.
- La proposition de configuration dépend d’un client authentifié ; sans lui,
  le contrat est écrit à la main puis contrôlé par `configure validate`.
- Aucun résultat n’est conservé et aucun état de workflow n’est introduit ;
  ces capacités relèvent des incréments suivants du plan.
