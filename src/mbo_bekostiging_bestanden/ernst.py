"""Ernst-niveaus voor kwaliteitsmeldingen (#238).

Leaf-module zonder afhankelijkheden: zowel ``waardenlijsten.py`` (dat via
``transform.py`` ván ``quality.py`` afhangt) als ``quality.py`` gebruiken
dezelfde vocabulaire, zonder een cyclische import.
"""

ERROR = "error"
WARNING = "warning"
INFO = "info"
