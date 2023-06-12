Per usare questa funzionalità, entrare in un console Python e usare questi comandi:

.. code-block:: python
    sys.path.extend(['/home/developer/Sviluppo/odoogenerator'])
    from main import odoogenerator
    o = odoogenerator.Connection(['14.0', '12.0'])
    o._create_venv()

Questo creerà nella cartella `Sviluppo` dell'utente corrente una cartella `Odoo` e una cartella `odoo<versione>` in cui verrà installato Odoo alla versione presente nella configurazione e creato un file di configurazione `.odoorc`

La configurazione è nella cartella dell'utente `./Sviluppo/srvmngt/odoogenerator_config` e si compone di due file:

#. un file txt con i requirements aggiuntivi specifici (i requirements di Odoo sono già installati di default, oltre a quelli di l10n-italy, da verificare se installare anche quelli delle altre repositories)
#. un file json con le specifiche per l'installazione.
