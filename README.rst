==============
Odoo Generator
==============

Questa applicazione effettua il download dei sorgenti Odoo e prepara un virtualenv.

Pre-requisiti:

.. code-block:: bash

    sudo apt install libmysqlclient-dev

Per usare questa funzionalità, eseguire:

.. code-block:: bash

<<<<<<< HEAD
    import sys
    sys.path.extend(['/home/developer/Sviluppo/odoogenerator'])
    from main import odoogenerator
    o = odoogenerator.Connection("16.0"|"14.0"|"12.0")
    o._create_venv()
=======
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ./main/odoogenerator.py --version 14.0
>>>>>>> b11f449 (black + main function)

Questo creerà nella cartella `Sviluppo` dell'utente corrente una cartella `Odoo` con una sotto-cartella `odoo<versione>` in cui verrà installato Odoo alla versione presente nella configurazione e creato un file di configurazione `.odoorc`

La configurazione è nella cartella dell'utente `./Sviluppo/srvmngt/odoogenerator_config` e si compone di due file:

#. un file txt con i requirements aggiuntivi specifici (i requirements di Odoo sono già installati di default, oltre a quelli di l10n-italy, da verificare se installare anche quelli delle altre repositories)
#. un file json con le specifiche per l'installazione.
