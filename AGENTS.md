# AGENTS.md

## Cel projektu
Aplikacja służy do przygotowywania list (Rozpisek) do gry.

Główne obszary:
- Rozpiski
- Armie
- Zbrojownie

Zależności:
- Rozpiski są budowane na podstawie Armii.
- Armie są budowane na podstawie Zbrojowni.
- Zasady gry znajdują się w `app/static/docs` i są źródłem prawdy.

## Model danych i dziedziczenie
- Armie i Rozpiski muszą wspierać hierarchię i dziedziczenie.
- Wariant ma przechowywać tylko różnice względem bazy.
- Nie duplikuj pełnego stanu, jeśli wystarczą nadpisania.
- Zachowuj stabilne identyfikatory obiektów, jeśli już istnieją.
- Zmiana modelu danych musi uwzględniać wpływ na warianty potomne.

## Baza danych
- Traktuj bazę jako środowisko testowe, ale współdzielone.
- Nie wykonuj destrukcyjnych operacji bez wyraźnego polecenia.
- Jeśli zadanie wymaga migracji lub zmian danych, opisz ich wpływ i przygotuj proces migracji.

## Użytkownicy i uprawnienia
- System ma mieć dwa poziomy dostępu:
  - `admin`
  - `user`
- Funkcje administracyjne muszą być jawnie odseparowane od zwykłego użytkownika.
- Nie rozszerzaj uprawnień użytkownika bez wyraźnego wymagania.

## Dokumentacja reguł
- Pliki w `app/static/docs` są tylko do odczytu.
- Nie modyfikuj ich bez osobnego zadania.
- Jeśli kod i dokumentacja są sprzeczne, zatrzymaj się i opisz rozbieżność.
- Nie zgaduj znaczenia reguły, jeśli nie wynika ono jasno z dokumentu lub kodu.

## Zasady pracy
- Najpierw czytaj istniejący kod, potem edytuj.
- Dla zadań wieloetapowych najpierw przygotuj krótki plan.
- Dla zadań prostych wykonuj minimalny lokalny patch.
- Nie przebudowuj architektury bez potrzeby.
- Preferuj małe, odwracalne zmiany.

## Testy i weryfikacja
- Po zmianie logiki uruchom testy związane z dotkniętym obszarem.
- Po zmianie UI sprawdź też stan pusty, błędny i podstawowy scenariusz.
- Jeśli testów brakuje, dodaj minimalny test regresji.
- Nie uznawaj zadania za zakończone bez krótkiej weryfikacji diffu.

## Konwencje zmian
- Nie zmieniaj formatowania poza zakresem zadania.
- Nie wprowadzaj dodatkowych refaktorów przy okazji małej zmiany.
- Jeśli poprawiasz błąd, opisz przyczynę i zakres poprawki.
- Jeśli zmieniasz model dziedziczenia, sprawdź zgodność z edycją wariantów potomnych.

## Komendy projektu
- Install: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt`
- Run: `make dev`
- Test: `make test`

## Oczekiwany sposób pracy agenta
- Przed zmianą wskaż pliki, które zamierzasz edytować.
- Odczytuj pliki batchami
- Jeśli wymaganie jest niejasne, najpierw wypisz założenia i braki.
- Po wykonaniu zmian podaj:
  - co zmieniono
  - jak zweryfikowano
  - co nadal wymaga decyzji