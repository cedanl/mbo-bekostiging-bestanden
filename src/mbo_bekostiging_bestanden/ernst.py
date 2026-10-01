"""Ernst-niveaus voor kwaliteitsmeldingen (#238).

Leaf-module zonder afhankelijkheden: zowel ``waardenlijsten.py`` (dat ook de
sterbouw gebruikt) als ``quality.py`` gebruiken dezelfde vocabulaire, zonder
een cyclische import.
"""

ERROR = "error"
WARNING = "warning"
INFO = "info"
