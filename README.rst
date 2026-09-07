==============
Odoo Generator
==============

Questa applicazione effettua il download dei sorgenti Odoo, gestisce i repository aggiuntivi e prepara un ambiente virtuale utilizzando `uv`.

Pre-requisiti:

.. code-block:: bash

    sudo apt install libmysqlclient-dev
    curl -LsSf https://astral.sh/uv/install.sh | sh

Utilizzo:

.. code-block:: bash

    uv run ./main/odoogenerator.py --version 14.0

L'applicazione creerà in `~/Sviluppo/Odoo/odoo<versione>` un ambiente con Odoo, i repository configurati e il file `.odoorc`.

Opzioni:

* `-V, --version`: Versione di Odoo (es. 14.0, 16.0, 18.0). Default: 14.0.
* `-P, --private yes`: Include i repository privati.
* `-G, --gitaggregate yes`: Esegue `gitaggregate` durante la generazione.
* `-S, --save-only yes`: Genera solo il file `.odoorc` senza creare l'ambiente.
* `-T, --translate-repo <repo>`: Estrae le traduzioni `it.po` per il repository indicato.

Configurazione:
I file di configurazione (`.json` per i repository e `.txt` per i requirements) si trovano in `~/Sviluppo/srvmngt/odoogenerator_config/`.

# TODO
Nella progetto Odoo generato, il file pyproject.toml conterrà i requirements alle varie librerie con sia le versioni specifiche, che la versione generica del pacchetto quando sono nominate entrambe. In questo caso, le versioni generiche vanno rimosse manualmente, per proseguire l'avvio del progetto. In seguito si spera di rimuovere questo errore.
