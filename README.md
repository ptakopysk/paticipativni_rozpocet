# Participativní rozpočet — Python CGI

Tři české stránky: `index.cgi` pro mobilní hlasování, `admin.cgi` pro správu a `results.cgi` pro projektor. Rozpočet každého hlasujícího je přesně 4 000 000 000 EUR (4 000 milionů), rozdělovaný po 1 000 000 EUR. Výsledky se obnovují každých 5 sekund.

Python 3.9+ na Linuxu/Unixu, pouze standardní knihovna. Žádná databáze, framework, instalace balíčků ani vlastní naslouchající port. CGI spouští stávající webový server.

## Nasazení na hosting s CGI

1. Nahrajte celý projekt. Webový kořen nasměrujte **výhradně na adresář `public/`**. Složky `src/`, `bin/` a `storage/` musí zůstat mimo veřejný webový kořen.
2. Povolte Python CGI. U Apache je potřeba `mod_cgi`/`mod_cgid`, `Options +ExecCGI` a `AddHandler cgi-script .cgi`. Přiložený `public/.htaccess` funguje, pokud hosting dovoluje příslušné direktivy (`AllowOverride Options FileInfo Indexes`). Při konfiguraci přes správce serveru nastavte stejná pravidla v konfiguraci. Některé hostingy vyžadují adresář `cgi-bin`; v takovém případě nastavte tento adresář jako veřejný adresář aplikace a zachovejte sourozenecké `src/` a `storage/`, případně upravte cestu v CGI souborech. Styly a JavaScript obsluhuje `assets.cgi`, takže fungují i pod `ScriptAlias`, kde Apache považuje všechny soubory za CGI. Adresář `assets/` ponechte vedle něj; soubory CSS a JS se nespouštějí přímo.
3. Soubory `public/*.cgi` musí být spustitelné (`chmod 755 public/*.cgi`) a mít unixové konce řádků. První řádek je `#!/usr/bin/env python3`; pokud hosting vyžaduje přesnou cestu, změňte jej například na `#!/usr/bin/python3`.
4. Spusťte `python3 bin/setup.py` a zadejte heslo správce dvakrát (minimálně 12 znaků). To lze provést i lokálně a následně bezpečně nahrát vytvořený `storage/config.json`. Heslo se ukládá jako PBKDF2 hash. Konfigurační soubor obsahuje také tajný klíč; nezveřejňujte jej.
5. Uživatel, pod kterým běží CGI, potřebuje čtení konfigurace a čtení/zápis do `storage/`. Setup vytváří konfiguraci s oprávněním 600, takže musí běžet pod stejným uživatelem jako CGI, nebo správce musí nastavit vlastnictví a přístup příslušné skupiny. Nepoužívejte veřejný zápis 777. Alternativní úložiště nastavíte proměnnou prostředí `BUDGET_STORAGE` (stejně pro setup i CGI).
6. Otevřete `admin.cgi`, přihlaste se a vložte projekty, každý na samostatný řádek. Sdílejte `index.cgi` s účastníky a promítejte `results.cgi`. Používejte HTTPS.

Po prvním hlasu je seznam projektů uzamčený. Zahájení nového kola vymaže předchozí hlasy a umožní znovu hlasovat. Před resetem si udělejte zálohu. Změna hesla opětovným spuštěním setupu také vymění podpisový klíč a zneplatní cookies; dělejte ji mezi koly, protože tím lze znovu hlasovat s novou identitou.

## Ukládání a omezení

`storage/state.json` obsahuje projekty a anonymní rozdělení hlasů. Souběžné požadavky chrání `flock` na samostatném souboru; zápis probíhá přes dočasný soubor a atomické přejmenování. Použijte lokální disk s podporou těchto operací, nikoli sdílené úložiště bez spolehlivého zamykání. Zálohujte `state.json` i `config.json`; při kopírování za provozu je nutné respektovat `state.lock`, nebo na chvíli zastavit hlasování.

Omezení jednoho hlasu za kolo je založené na podepsané cookie prohlížeče, nikoli na ověření osoby. Smazání cookies či jiný prohlížeč umožní další hlas. Pro závazné veřejné volby by bylo nutné přidat individuální hlasovací kódy nebo přihlášení. Administrace používá heslo, podepsanou cookie s platností 8 hodin a CSRF ochranu. Při veřejném provozu lze na webserveru přidat omezení pokusů o přihlášení.

Součty na projektoru jsou součtem všech přidělených peněz: při 10 hlasech tedy 40 miliard EUR. Procenta ukazují podíl projektu na tomto součtu.

## Ověření

`python3 -m unittest discover -s tests -v`

Testy spouštějí CGI přímo s CGI proměnnými prostředí a izolovaným dočasným úložištěm; nepotřebují server ani port. Ověření skutečné konfigurace CGI na cílovém hostingu je potřeba provést po nasazení.

## Když aplikace po setupu nefunguje

Spusťte `python3 bin/check.py`. Výpis ukáže skutečnou složku úložiště, UID uživatele, vlastníky a práva souborů a ověří čtení konfigurace, zamykání i zápis bez změny hlasů. Nesdílí heslo ani podpisový klíč. Pokud test v terminálu projde, ale web nefunguje, CGI pravděpodobně běží pod jiným uživatelem nebo má jiné `BUDGET_STORAGE`. Setup ukládá konfiguraci s právy 600, takže ji standardně přečte pouze vlastník. Vlastnictví či skupinová práva musí odpovídat skutečnému uživateli CGI, včetně práva procházet všechny nadřazené adresáře. Nepřepínejte konfiguraci na veřejně čitelnou.

Stránka rozlišuje chybějící konfiguraci, odepřený přístup a poškozené soubory. Úplné podrobnosti včetně cesty a tracebacku zapisuje do chybového logu webserveru za textem `Budget CGI error`. Opakovaný setup není řešením chybných práv a zneplatní stávající cookies.

### Hosting, kde CGI běží jako jiný uživatel

Chyba `Permission denied: .../storage/config.json` znamená, že účet CGI nemůže přečíst konfiguraci (nebo projít některý nadřazený adresář). Zjistěte u správce hostingu skutečnou skupinu CGI. Pro úložiště lze pak použít například níže uvedené příkazy; `CGI_GROUP` nahraďte skutečnou skupinou, ke které má CGI přístup. Změna skupiny může vyžadovat správce serveru.

```sh
chgrp CGI_GROUP storage storage/config.json
chmod 2770 storage
chmod 640 storage/config.json
```

Pokud již existují `state.lock` a `state.json`, musí je CGI také umět číst a zapisovat. Je potřeba povolit skupině CGI přístup k těmto konkrétním souborům a průchod nadřazenými adresáři. Nezveřejňujte konfiguraci pomocí `chmod 644` a nenastavujte `777`.

Chyby `exec of .../assets/style.css failed` nebo `.../assets/app.js failed` řeší načítání přes přiložené `assets.cgi`. Nahrajte aktualizovaný `src/app.py` a spustitelný `public/assets.cgi` (755).

Styly a JavaScript se nyní načítají přes existující vstupní skript `index.cgi?asset=app.js&v=4000` (resp. `style.css`), se správným MIME typem a bez závislosti na nasazení nového CGI souboru. Starší `assets.cgi` zůstává kompatibilní. Po přechodu z rozpočtu 4 milionů na 4 miliardy zahajte nové kolo, pokud již obsahuje hlasy. Staré hlasy se automaticky nemažou ani nenásobí. Částky lze také zadat do číselných polí vedle posuvníků.
