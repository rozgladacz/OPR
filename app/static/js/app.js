const abilityDefinitionsCache = new Map();

function initAbilityPicker(root) {
  const definitionsData = root.dataset.definitions || '';
  let definitions;
  if (abilityDefinitionsCache.has(definitionsData)) {
    definitions = abilityDefinitionsCache.get(definitionsData);
  } else {
    definitions = definitionsData ? JSON.parse(definitionsData) : [];
    abilityDefinitionsCache.set(definitionsData, definitions);
  }
  const definitionMap = new Map(definitions.map((item) => [item.slug, item]));
  const targetId = root.dataset.targetInput;
  const hiddenInput = targetId ? document.getElementById(targetId) : root.querySelector('input[type="hidden"]');
  const selectEl = root.querySelector('.ability-picker-select');
  const valueContainer = root.querySelector('.ability-picker-value');
  const valueInput = root.querySelector('.ability-picker-value-input');
  const valueSelect = root.querySelector('.ability-picker-value-select');
  const addButton = root.querySelector('.ability-picker-add');
  const listEl = root.querySelector('.ability-picker-list');
  const allowDefaultToggle = root.dataset.defaultToggle === 'true';
  const defaultInitial = root.dataset.defaultInitial === 'true';
  const allowMandatoryToggle = root.dataset.mandatoryToggle === 'true';
  const mandatoryInitial = root.dataset.mandatoryInitial === 'true';
  const allowCustomName = root.dataset.allowCustomName === 'true';
  const hideOwnedAbilities = root.dataset.hideOwnedAbilities === 'true';
  let isUpdatingSelectOptions = false;
  let items = [];

  function getDefinition(slug) {
    if (!slug) {
      return null;
    }
    return definitionMap.get(slug) || null;
  }

  function formatLabel(definition, value, choiceLabel) {
    const displayValue = (choiceLabel || value || '').toString().trim();
    if (!definition) {
      return displayValue;
    }
    if (definition.slug === 'aura') {
      if (choiceLabel) {
        return choiceLabel;
      }
      if (value) {
        const [abilityRef, rangeRefRaw] = String(value).split('|', 2);
        const rangeRef = (rangeRefRaw || '').trim().replace(/["”]/g, '');
        const isLongRange = rangeRef === '12';
        const prefix = isLongRange ? `${definition.name}(12")` : definition.name;
        const abilityLabel = (abilityRef || '').trim();
        return abilityLabel ? `${prefix}: ${abilityLabel}` : prefix;
      }
      return definition.display_name || definition.name;
    }
    if (definition.slug === 'rozkaz') {
      const valueLabel = displayValue || value || '';
      return valueLabel
        ? `${definition.name}: ${valueLabel}`
        : definition.display_name || definition.name;
    }
    if (definition.requires_value) {
      return displayValue ? `${definition.name}(${displayValue})` : definition.display_name;
    }
    return definition.name;
  }

  function descriptionFor(item) {
    if (item.description) {
      return item.description;
    }
    const definition = getDefinition(item.slug);
    return definition ? definition.description : '';
  }

  function normalizeEntry(entry) {
    const slug = entry.slug || '';
    const definition = getDefinition(slug);
    const rawValue = entry.value !== undefined && entry.value !== null ? String(entry.value) : '';
    const rawLabel = entry.raw !== undefined && entry.raw !== null ? String(entry.raw) : '';
    const label = entry.label || formatLabel(definition, rawValue, rawLabel);
    const abilityId = entry.ability_id ?? (definition && Object.prototype.hasOwnProperty.call(definition, 'ability_id') ? definition.ability_id : null);
    let isDefault = allowDefaultToggle ? Boolean(entry.is_default ?? defaultInitial) : false;
    const isMandatory = allowMandatoryToggle
      ? Boolean(entry.is_mandatory ?? mandatoryInitial)
      : Boolean(entry.is_mandatory ?? false);
    if (allowDefaultToggle && isMandatory && !isDefault) {
      isDefault = true;
    }
    const baseLabel = entry.base_label || label || rawLabel || rawValue;
    let customName = '';
    if (typeof entry.custom_name === 'string') {
      customName = entry.custom_name.trim().slice(0, ABILITY_NAME_MAX_LENGTH);
    }
    return {
      slug,
      value: rawValue,
      raw: rawLabel || rawValue || baseLabel,
      label: baseLabel || rawLabel || rawValue,
      base_label: baseLabel || '',
      custom_name: customName,
      ability_id: abilityId,
      is_default: isDefault,
      is_mandatory: isMandatory,
      description: entry.description || descriptionFor({ slug }),
    };
  }

  function abilityKey(item) {
    if (!item) {
      return '';
    }
    const slug = (item.slug || '').toString().trim().toLowerCase();
    const value = (item.value || '').toString().trim().toLowerCase();
    const raw = (item.raw || item.label || '').toString().trim().toLowerCase();
    if (!slug || slug === '__custom__') {
      return raw ? `custom::${raw}` : '';
    }
    if (slug === 'aura' || slug === 'rozkaz') {
      return `${slug}::${value || raw}`;
    }
    if (slug === 'rozprysk' || slug === 'zabojczy') {
      return slug;
    }
    return slug;
  }

  function isDuplicateAbility(entry) {
    const key = abilityKey(entry);
    if (!key) {
      return false;
    }
    return items.some((existing) => abilityKey(existing) === key);
  }

  function parseInitial() {
    if (!hiddenInput || !hiddenInput.value) {
      items = [];
      return;
    }
    try {
      const parsed = JSON.parse(hiddenInput.value);
      if (Array.isArray(parsed)) {
        items = parsed.map((entry) => normalizeEntry(entry || {}));
      }
    } catch (err) {
      console.warn('Nie udało się odczytać wybranych zdolności', err);
      items = [];
    }
  }

  function updateHidden() {
    if (!hiddenInput) {
      return;
    }
    const safeItems = items.map((entry) => {
      const payload = {
        slug: entry.slug,
        value: entry.value,
        label: entry.label,
        raw: entry.raw,
        ability_id: entry.ability_id ?? null,
        is_default: entry.is_default ?? false,
      };
      if (allowMandatoryToggle || entry.is_mandatory) {
        payload.is_mandatory = Boolean(entry.is_mandatory);
      }
      if (allowCustomName) {
        const customName = typeof entry.custom_name === 'string' ? entry.custom_name.trim() : '';
        if (customName) {
          payload.custom_name = customName.slice(0, ABILITY_NAME_MAX_LENGTH);
        }
      }
      if (entry.base_label) {
        payload.base_label = entry.base_label;
      }
      return payload;
    });
    hiddenInput.value = JSON.stringify(safeItems);
  }

  function moveItem(fromIndex, toIndex) {
    if (!Array.isArray(items)) {
      return;
    }
    const lastIndex = items.length - 1;
    if (
      fromIndex === toIndex ||
      fromIndex < 0 ||
      toIndex < 0 ||
      fromIndex > lastIndex ||
      toIndex > lastIndex
    ) {
      return;
    }
    const [entry] = items.splice(fromIndex, 1);
    items.splice(toIndex, 0, entry);
    updateHidden();
    renderList();
  }

  function renderList() {
    if (!listEl) {
      return;
    }
    listEl.innerHTML = '';
    if (!items.length) {
      const empty = document.createElement('p');
      empty.className = 'text-muted mb-0';
      empty.textContent = 'Brak wybranych zdolności.';
      listEl.appendChild(empty);
      updateSelectOptionVisibility();
      return;
    }
    const wrapper = document.createElement('div');
    wrapper.className = 'd-flex flex-column gap-2';
    items.forEach((item, index) => {
      const row = document.createElement('div');
      row.className = 'border rounded p-2 d-flex flex-wrap align-items-center gap-2';

      const labelWrapper = document.createElement('div');
      labelWrapper.className = 'flex-grow-1 d-flex flex-column gap-2';
      const baseLabel = item.base_label || item.label || item.raw || item.slug;
      const desc = descriptionFor(item);
      const labelText = document.createElement('div');
      labelText.textContent = formatAbilityDisplayLabel(baseLabel, item.custom_name) || baseLabel;
      if (desc) {
        labelText.title = desc;
      }
      labelWrapper.appendChild(labelText);

      if (allowCustomName) {
        const inputWrapper = document.createElement('div');
        inputWrapper.className = 'd-flex flex-column';
        const inputLabel = document.createElement('label');
        inputLabel.className = 'form-label mb-1 small text-muted';
        const inputId = `ability-picker-name-${index}-${Math.random().toString(16).slice(2)}`;
        inputLabel.setAttribute('for', inputId);
        inputLabel.textContent = 'Nazwa własna (opcjonalnie)';
        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.className = 'form-control form-control-sm';
        nameInput.id = inputId;
        nameInput.placeholder = 'Np. Medyk';
        nameInput.maxLength = ABILITY_NAME_MAX_LENGTH;
        nameInput.value = item.custom_name || '';
        const applyValue = (value) => {
          const limited = typeof value === 'string' ? value.slice(0, ABILITY_NAME_MAX_LENGTH) : '';
          if (limited !== nameInput.value) {
            nameInput.value = limited;
          }
          const normalized = limited.trim();
          item.custom_name = normalized;
          labelText.textContent = formatAbilityDisplayLabel(baseLabel, normalized) || baseLabel;
          updateHidden();
        };
        nameInput.addEventListener('input', () => {
          applyValue(nameInput.value);
        });
        nameInput.addEventListener('change', () => {
          applyValue(nameInput.value);
        });
        nameInput.addEventListener('keydown', (event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            nameInput.blur();
          }
        });
        inputWrapper.appendChild(inputLabel);
        inputWrapper.appendChild(nameInput);
        labelWrapper.appendChild(inputWrapper);
      }

      row.appendChild(labelWrapper);

      if (allowDefaultToggle || allowMandatoryToggle) {
        const toggleWrapper = document.createElement('div');
        toggleWrapper.className = 'd-flex flex-column gap-1 mb-0';

        let defaultInput;
        let mandatoryInput;

        const syncDefaultState = () => {
          if (!allowDefaultToggle || !defaultInput) {
            return;
          }
          const shouldDisable = allowMandatoryToggle && Boolean(item.is_mandatory);
          defaultInput.disabled = shouldDisable;
          if (shouldDisable) {
            defaultInput.checked = true;
            item.is_default = true;
          }
        };

        if (allowDefaultToggle) {
          const defaultWrapper = document.createElement('div');
          defaultWrapper.className = 'form-check mb-0';
          defaultInput = document.createElement('input');
          defaultInput.type = 'checkbox';
          defaultInput.className = 'form-check-input';
          defaultInput.id = `ability-default-${index}-${Math.random().toString(16).slice(2)}`;
          defaultInput.checked = Boolean(item.is_default);
          defaultInput.addEventListener('change', () => {
            const checked = defaultInput.checked;
            item.is_default = checked;
            if (!checked && allowMandatoryToggle && item.is_mandatory) {
              item.is_mandatory = false;
              if (mandatoryInput) {
                mandatoryInput.checked = false;
              }
              syncDefaultState();
            }
            updateHidden();
          });
          const defaultLabel = document.createElement('label');
          defaultLabel.className = 'form-check-label small';
          defaultLabel.setAttribute('for', defaultInput.id);
          defaultLabel.textContent = 'Domyślna';
          defaultWrapper.appendChild(defaultInput);
          defaultWrapper.appendChild(defaultLabel);
          toggleWrapper.appendChild(defaultWrapper);
        }

        if (allowMandatoryToggle) {
          const mandatoryWrapper = document.createElement('div');
          mandatoryWrapper.className = 'form-check mb-0';
          mandatoryInput = document.createElement('input');
          mandatoryInput.type = 'checkbox';
          mandatoryInput.className = 'form-check-input';
          mandatoryInput.id = `ability-mandatory-${index}-${Math.random().toString(16).slice(2)}`;
          mandatoryInput.checked = Boolean(item.is_mandatory);
          mandatoryInput.addEventListener('change', () => {
            const checked = mandatoryInput.checked;
            item.is_mandatory = checked;
            if (checked && allowDefaultToggle && defaultInput && !defaultInput.checked) {
              defaultInput.checked = true;
              item.is_default = true;
            }
            syncDefaultState();
            updateHidden();
          });
          const mandatoryLabel = document.createElement('label');
          mandatoryLabel.className = 'form-check-label small';
          mandatoryLabel.setAttribute('for', mandatoryInput.id);
          mandatoryLabel.textContent = 'Obowiązkowe';
          mandatoryWrapper.appendChild(mandatoryInput);
          mandatoryWrapper.appendChild(mandatoryLabel);
          toggleWrapper.appendChild(mandatoryWrapper);
        }

        syncDefaultState();
        row.appendChild(toggleWrapper);
      }

      const controlsWrapper = document.createElement('div');
      controlsWrapper.className = 'd-flex flex-column flex-sm-row gap-2';

      const reorderGroup = document.createElement('div');
      reorderGroup.className = 'btn-group-vertical';
      const moveUpBtn = document.createElement('button');
      moveUpBtn.type = 'button';
      moveUpBtn.className = 'btn btn-outline-secondary btn-sm';
      moveUpBtn.textContent = '↑';
      moveUpBtn.setAttribute('aria-label', 'Przesuń w górę');
      moveUpBtn.disabled = index === 0;
      moveUpBtn.addEventListener('click', (event) => {
        event.preventDefault();
        moveItem(index, index - 1);
      });
      const moveDownBtn = document.createElement('button');
      moveDownBtn.type = 'button';
      moveDownBtn.className = 'btn btn-outline-secondary btn-sm';
      moveDownBtn.textContent = '↓';
      moveDownBtn.setAttribute('aria-label', 'Przesuń w dół');
      moveDownBtn.disabled = index === items.length - 1;
      moveDownBtn.addEventListener('click', (event) => {
        event.preventDefault();
        moveItem(index, index + 1);
      });
      reorderGroup.appendChild(moveUpBtn);
      reorderGroup.appendChild(moveDownBtn);
      controlsWrapper.appendChild(reorderGroup);

      const removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'btn btn-outline-danger btn-sm';
      removeBtn.textContent = 'Usuń';
      removeBtn.addEventListener('click', () => {
        items.splice(index, 1);
        updateHidden();
        renderList();
      });
      controlsWrapper.appendChild(removeBtn);

      row.appendChild(controlsWrapper);

      wrapper.appendChild(row);
    });
    listEl.appendChild(wrapper);

    updateSelectOptionVisibility();
  }

  function updateSelectOptionVisibility() {
    if (!hideOwnedAbilities || !selectEl) {
      return;
    }
    const usedKeys = new Set(
      items
        .map((entry) => abilityKey(entry))
        .filter((key) => typeof key === 'string' && key)
    );
    let selectionCleared = false;
    Array.from(selectEl.options).forEach((option) => {
      if (!option.value) {
        option.hidden = false;
        option.disabled = false;
        return;
      }
      const definition = getDefinition(option.value);
      const optionKey = abilityKey({
        slug: definition ? definition.slug : option.value,
      });
      const shouldHide = optionKey ? usedKeys.has(optionKey) : false;
      option.hidden = shouldHide;
      option.disabled = shouldHide;
      if (shouldHide && option.selected) {
        selectionCleared = true;
      }
    });
    if (selectionCleared) {
      selectEl.value = '';
      if (!isUpdatingSelectOptions) {
        isUpdatingSelectOptions = true;
        handleSelectChange();
        isUpdatingSelectOptions = false;
      }
    }
  }

  function resetValueInputs() {
    if (valueInput) {
      valueInput.value = '';
      valueInput.classList.remove('is-invalid');
      valueInput.type = 'text';
    }
    if (valueSelect) {
      valueSelect.value = '';
    }
  }

  function populateValueChoices(definition) {
    if (!valueSelect) {
      return;
    }
    valueSelect.innerHTML = '';
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = definition.value_label ? `Wybierz (${definition.value_label})` : 'Wybierz wartość';
    valueSelect.appendChild(placeholder);
    (definition.value_choices || []).forEach((choice) => {
      const option = document.createElement('option');
      if (typeof choice === 'string') {
        option.value = choice;
        option.textContent = choice;
      } else if (choice && typeof choice === 'object') {
        option.value = choice.value ?? '';
        option.textContent = choice.label || choice.value || '';
        if (choice.description) {
          option.title = choice.description;
        }
      }
      valueSelect.appendChild(option);
    });
  }

  function handleSelectChange() {
    if (!selectEl || !valueContainer) {
      return;
    }
    resetValueInputs();
    const slug = selectEl.value;
    const definition = getDefinition(slug);
    if (definition && definition.requires_value) {
      valueContainer.classList.remove('d-none');
      if (definition.value_choices && definition.value_choices.length > 0 && valueSelect) {
        valueSelect.classList.remove('d-none');
        populateValueChoices(definition);
        if (valueInput) {
          valueInput.classList.add('d-none');
        }
      } else {
        if (valueSelect) {
          valueSelect.classList.add('d-none');
          valueSelect.innerHTML = '';
        }
        if (valueInput) {
          valueInput.classList.remove('d-none');
          valueInput.placeholder = definition.value_label ? `Wartość (${definition.value_label})` : 'Wartość';
          valueInput.type = definition.value_type === 'number' ? 'number' : 'text';
        }
      }
    } else {
      valueContainer.classList.add('d-none');
      if (valueSelect) {
        valueSelect.classList.add('d-none');
        valueSelect.innerHTML = '';
      }
    }
  }

  function validateValue(definition, value) {
    if (!definition || !definition.requires_value) {
      return true;
    }
    const trimmed = value.trim();
    if (!trimmed) {
      return false;
    }
    if (definition.value_type === 'number') {
      return !Number.isNaN(Number(trimmed));
    }
    return true;
  }

  function handleAdd() {
    if (!selectEl) {
      return;
    }
    const slug = selectEl.value;
    if (!slug) {
      return;
    }
    const definition = getDefinition(slug);
    let rawValue = '';
    let choiceLabel = '';
    if (definition && definition.requires_value) {
      if (definition.value_choices && definition.value_choices.length > 0 && valueSelect) {
        rawValue = valueSelect.value || '';
        const option = valueSelect.selectedOptions[0];
        choiceLabel = option ? option.textContent.trim() : '';
        if (!rawValue) {
          return;
        }
      } else if (valueInput) {
        rawValue = valueInput.value || '';
        if (!validateValue(definition, rawValue)) {
          valueInput.classList.add('is-invalid');
          valueInput.addEventListener(
            'input',
            () => valueInput.classList.remove('is-invalid'),
            { once: true }
          );
          return;
        }
      }
    }
    const label = definition
      ? formatLabel(definition, rawValue, choiceLabel)
      : selectEl.selectedOptions[0]?.textContent || slug;
    const entry = normalizeEntry({
      slug: definition ? definition.slug : '__custom__',
      value: rawValue.trim(),
      raw: choiceLabel,
      label,
      ability_id: definition && Object.prototype.hasOwnProperty.call(definition, 'ability_id')
        ? definition.ability_id
        : null,
      is_default: allowDefaultToggle ? defaultInitial : false,
    });
    if (isDuplicateAbility(entry)) {
      if (selectEl) {
        selectEl.classList.add('is-invalid');
        selectEl.addEventListener(
          'change',
          () => selectEl.classList.remove('is-invalid'),
          { once: true },
        );
      }
      return;
    }
    items.push(entry);
    updateHidden();
    renderList();
    selectEl.value = '';
    handleSelectChange();
  }

  if (addButton) {
    addButton.addEventListener('click', handleAdd);
  }
  if (selectEl) {
    selectEl.addEventListener('change', handleSelectChange);
  }

  parseInitial();
  renderList();
  handleSelectChange();
  updateSelectOptionVisibility();

  root.abilityPicker = {
    setItems(newItems) {
      items = Array.isArray(newItems) ? newItems.map((entry) => normalizeEntry(entry || {})) : [];
      updateHidden();
      renderList();
      updateSelectOptionVisibility();
    },
  };
}

function initAbilityPickers() {
  document.querySelectorAll('[data-ability-picker]').forEach((element) => {
    initAbilityPicker(element);
  });
}

const RANGE_TABLE = { 0: 0.6, 12: 0.65, 18: 1.0, 24: 1.25, 30: 1.45, 36: 1.55 };
const AP_BASE = { '-1': 0.8, 0: 1.0, 1: 1.5, 2: 1.9, 3: 2.25, 4: 2.5, 5: 2.65 };
const AP_NO_COVER = { '-1': 0.1, 0: 0.25, 1: 0.2, 2: 0.15, 3: 0.1, 4: 0.1, 5: 0.05 };
const AP_LANCE = { '-1': 0.15, 0: 0.35, 1: 0.3, 2: 0.25, 3: 0.15, 4: 0.1, 5: 0.05 };
const AP_CORROSIVE = { '-1': 0.05, 0: 0.05, 1: 0.1, 2: 0.25, 3: 0.4, 4: 0.5, 5: 0.55 };
const BLAST_MULTIPLIER = { 2: 1.95, 3: 2.8, 6: 4.3 };
const DEADLY_MULTIPLIER = { 2: 1.9, 3: 2.6, 6: 3.8 };
const CLASSIFICATION_SLUGS = new Set(['wojownik', 'strzelec']);
const ABILITY_NAME_MAX_LENGTH = 60;

function splitTraits(text) {
  if (!text) {
    return [];
  }
  if (Array.isArray(text)) {
    return text;
  }
  return String(text)
    .split(/[,;]/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}

function normalizeName(text) {
  if (text === undefined || text === null) {
    return '';
  }
  let value = String(text);
  try {
    value = value.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  } catch (err) {
    value = value
      .replace(/ą/g, 'a')
      .replace(/ć/g, 'c')
      .replace(/ę/g, 'e')
      .replace(/ł/g, 'l')
      .replace(/ń/g, 'n')
      .replace(/ó/g, 'o')
      .replace(/ś/g, 's')
      .replace(/ż/g, 'z')
      .replace(/ź/g, 'z');
  }
  value = value.replace(/[-_]/g, ' ');
  value = value.replace(/[!?]+$/g, '');
  value = value.replace(/\s+/g, ' ').trim();
  return value.toLowerCase();
}

function extractNumber(text) {
  if (text === undefined || text === null) {
    return 0;
  }
  const match = String(text).match(/[0-9]+(?:[.,][0-9]+)?/);
  if (!match) {
    return 0;
  }
  return Number(match[0].replace(',', '.'));
}

function abilityIdentifier(text) {
  if (text === undefined || text === null) {
    return '';
  }
  let base = String(text).trim();
  if (!base) {
    return '';
  }
  ['(', '=', ':'].forEach((separator) => {
    if (base.includes(separator)) {
      base = base.split(separator, 1)[0].trim();
    }
  });
  base = base.replace(/[“”]/g, '"');
  while (base.endsWith('?') || base.endsWith('!')) {
    base = base.slice(0, -1).trim();
  }
  return normalizeName(base);
}

function passiveIdentifier(text) {
  const ident = abilityIdentifier(text);
  if (ident) {
    return ident;
  }
  const norm = normalizeName(text);
  let trimmed = norm;
  while (trimmed.endsWith('?') || trimmed.endsWith('!')) {
    trimmed = trimmed.slice(0, -1).trim();
  }
  if (trimmed) {
    return trimmed;
  }
  return norm;
}

function parseFlagString(text) {
  if (!text) {
    return {};
  }
  const entries = String(text)
    .split(',')
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);
  const result = {};
  entries.forEach((entry) => {
    const separatorIndex = entry.indexOf('=');
    if (separatorIndex >= 0) {
      const key = entry.slice(0, separatorIndex).trim();
      const value = entry.slice(separatorIndex + 1).trim();
      if (key) {
        result[key] = value;
      }
    } else {
      result[entry] = true;
    }
  });
  return result;
}

function flagsToAbilityList(flags) {
  const abilities = [];
  Object.entries(flags || {}).forEach(([key, value]) => {
    if (key === undefined || key === null) {
      return;
    }
    let name = String(key).trim();
    if (!name) {
      return;
    }
    while (name.endsWith('?') || name.endsWith('!')) {
      name = name.slice(0, -1).trim();
    }
    const slug = abilityIdentifier(name) || normalizeName(name);
    if (typeof value === 'boolean') {
      if (value) {
        abilities.push(slug);
      }
      return;
    }
    if (value === null || value === undefined) {
      abilities.push(slug);
      return;
    }
    const trimmed = String(value).trim();
    if (!trimmed) {
      abilities.push(slug);
      return;
    }
    const lowered = trimmed.toLowerCase();
    if (lowered === 'true' || lowered === 'yes') {
      abilities.push(slug);
      return;
    }
    const numeric = Number(trimmed);
    if (Number.isFinite(numeric) && numeric > 0) {
      abilities.push(slug);
    }
  });
  return abilities;
}

function lookupWithNearest(table, key) {
  if (table === undefined || table === null) {
    return 0;
  }
  const numericKey = Number(key);
  if (Number.isFinite(numericKey) && Object.prototype.hasOwnProperty.call(table, numericKey)) {
    return Number(table[numericKey]);
  }
  const entries = Object.keys(table).map((entry) => Number(entry));
  if (!entries.length) {
    return 0;
  }
  const target = Number.isFinite(numericKey) ? numericKey : entries[0];
  let nearest = entries[0];
  let minDiff = Math.abs(nearest - target);
  entries.forEach((entry) => {
    const diff = Math.abs(entry - target);
    if (diff < minDiff) {
      nearest = entry;
      minDiff = diff;
    }
  });
  return Number(table[nearest]);
}

function rangeMultiplier(rangeValue) {
  const numeric = Number(rangeValue);
  if (Number.isFinite(numeric) && Object.prototype.hasOwnProperty.call(RANGE_TABLE, numeric)) {
    return RANGE_TABLE[numeric];
  }
  const keys = Object.keys(RANGE_TABLE).map((entry) => Number(entry));
  if (!keys.length) {
    return 1;
  }
  const target = Number.isFinite(numeric) ? numeric : keys[0];
  let nearest = keys[0];
  let minDiff = Math.abs(nearest - target);
  keys.forEach((entry) => {
    const diff = Math.abs(entry - target);
    if (diff < minDiff) {
      nearest = entry;
      minDiff = diff;
    }
  });
  return RANGE_TABLE[nearest];
}

function normalizeRangeValue(value) {
  if (value === undefined || value === null) {
    return 0;
  }
  if (typeof value === 'number') {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) {
      return 0;
    }
    return Math.round(numeric);
  }
  const text = String(value).trim();
  if (!text) {
    return 0;
  }
  const lowered = text.toLowerCase();
  if (['wręcz', 'wrecz', 'melee', 'm'].includes(lowered)) {
    return 0;
  }
  const numeric = extractNumber(text);
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return 0;
  }
  return Math.round(numeric);
}

function buildWeaponFlags(baseFlags, passiveItems, passiveState) {
  const result = { ...(baseFlags || {}) };
  const identifierKeys = new Map();
  Object.keys(baseFlags || {}).forEach((key) => {
    const ident = passiveIdentifier(key);
    if (!ident) {
      return;
    }
    if (!identifierKeys.has(ident)) {
      identifierKeys.set(ident, []);
    }
    identifierKeys.get(ident).push(key);
  });
  const stateMap = passiveState instanceof Map ? passiveState : new Map();
  (Array.isArray(passiveItems) ? passiveItems : []).forEach((entry) => {
    if (!entry || !entry.slug) {
      return;
    }
    const slug = String(entry.slug);
    const ident = passiveIdentifier(slug);
    const isMandatory = Boolean(entry.is_mandatory);
    const defaultCount = Number(entry.default_count ?? (entry.is_default ? 1 : 0));
    const defaultFlag = Number.isFinite(defaultCount) && defaultCount > 0 ? 1 : 0;
    const stored = stateMap.get(slug);
    const selectedFlag = isMandatory
      ? 1
      : Number.isFinite(stored)
        ? stored > 0
          ? 1
          : 0
        : defaultFlag;
    const enabled = selectedFlag > 0;
    const keys = identifierKeys.get(ident) || [];
    if (enabled) {
      if (keys.length) {
        const key = keys[0];
        const original = baseFlags ? baseFlags[key] : undefined;
        if (typeof original === 'boolean') {
          result[key] = true;
        } else if (original === null || original === '' || original === 0) {
          result[key] = true;
        } else if (original !== undefined) {
          result[key] = original;
        } else {
          result[key] = true;
        }
      } else {
        result[slug] = true;
      }
    } else if (keys.length) {
      keys.forEach((key) => {
        delete result[key];
      });
    } else {
      delete result[slug];
    }
  });
  return result;
}

function weaponCostInternal(quality, rangeValue, attacks, ap, weaponTraits, unitTraits, allowAssaultExtra = true) {
  let chance = 7;
  const attacksValue = Math.max(Number(attacks) || 0, 0);
  const apValue = Number.isFinite(Number(ap)) ? Number(ap) : 0;
  const normalizedRange = normalizeRangeValue(rangeValue);
  const rangeMod = rangeMultiplier(normalizedRange);
  let apMod = lookupWithNearest(AP_BASE, apValue);
  let mult = 1;
  let q = Number(quality);
  if (!Number.isFinite(q)) {
    q = 4;
  }
  const traitSet = new Set((Array.isArray(unitTraits) ? unitTraits : []).map((trait) => abilityIdentifier(trait)));
  const melee = normalizedRange === 0;

  if (melee && traitSet.has('furia')) {
    chance += 0.65;
  }
  if (!melee && traitSet.has('przygotowanie')) {
    chance += 0.65;
  }
  if (!melee && traitSet.has('wojownik')) {
    mult *= 0.5;
  }
  if (melee && traitSet.has('strzelec')) {
    mult *= 0.5;
  }
  if (!melee && traitSet.has('zle_strzela')) {
    q = 5;
  }
  if (!melee && traitSet.has('dobrze_strzela')) {
    q = 4;
  }

  let assault = false;
  let overcharge = false;
  const traitList = Array.isArray(weaponTraits) ? weaponTraits : splitTraits(weaponTraits);

  traitList.forEach((trait) => {
    const norm = normalizeName(trait);
    if (!norm) {
      return;
    }
    if (norm.startsWith('rozprysk') || norm.startsWith('blast')) {
      const value = Math.round(extractNumber(trait));
      if (BLAST_MULTIPLIER[value]) {
        mult *= BLAST_MULTIPLIER[value];
      }
      return;
    }
    if (norm.startsWith('zabojczy') || norm.startsWith('deadly')) {
      const value = Math.round(extractNumber(trait));
      if (DEADLY_MULTIPLIER[value]) {
        mult *= DEADLY_MULTIPLIER[value];
      }
      return;
    }
    if (['rozrywajacy', 'rozrywajaca', 'rozrwyajaca', 'rending'].includes(norm)) {
      chance += 1;
    } else if (['lanca', 'lance'].includes(norm)) {
      chance += 0.65;
    } else if (['namierzanie', 'lock on'].includes(norm)) {
      chance += 0.35;
      mult *= 1.1;
      apMod += lookupWithNearest(AP_NO_COVER, apValue);
    } else if (['impet', 'impact'].includes(norm)) {
      apMod += lookupWithNearest(AP_LANCE, apValue);
    } else if (['bez oslon', 'bez oslony', 'no cover'].includes(norm)) {
      apMod += lookupWithNearest(AP_NO_COVER, apValue);
    } else if (['zracy', 'corrosive'].includes(norm)) {
      apMod += lookupWithNearest(AP_CORROSIVE, apValue);
    } else if (['niebezposredni', 'indirect'].includes(norm)) {
      mult *= 1.2;
    } else if (['zuzywalny', 'limited'].includes(norm)) {
      mult *= 0.5;
    } else if (['precyzyjny', 'precise'].includes(norm)) {
      mult *= 1.5;
    } else if (['niezawodny', 'niezawodna', 'reliable'].includes(norm)) {
      q = 2;
    } else if (['szturmowy', 'szturmowa', 'assault'].includes(norm)) {
      assault = true;
    } else if (
      [
        'brutalny',
        'brutalna',
        'brutal',
        'bez regeneracji',
        'bez regegenracji',
        'no regen',
        'no regeneration',
      ].includes(norm)
    ) {
      mult *= 1.1;
    } else if (['podkrecenie', 'overcharge', 'overclock'].includes(norm)) {
      overcharge = true;
    }
  });

  chance = Math.max(chance - q, 1);
  let cost = attacksValue * 2 * rangeMod * chance * apMod * mult;

  if (overcharge && (!assault || normalizedRange !== 0)) {
    cost *= 1.4;
  }

  if (assault && allowAssaultExtra && normalizedRange !== 0) {
    const extra = weaponCostInternal(quality, 0, attacksValue, apValue, traitList, unitTraits, false);
    cost += extra;
  }

  return cost;
}

function buildWeaponCostMap(
  options,
  unitQuality,
  baseFlags,
  passiveItems,
  passiveState,
  classification,
) {
  const result = new Map();
  const weaponFlags = buildWeaponFlags(baseFlags, passiveItems, passiveState);
  if (classification && typeof classification === 'object' && classification.slug) {
    const slugText = String(classification.slug).trim();
    if (slugText) {
      const normalizedSlug = passiveIdentifier(slugText);
      let hasMatchingKey = false;
      Object.keys(weaponFlags).forEach((key) => {
        const ident = passiveIdentifier(key);
        if (CLASSIFICATION_SLUGS.has(ident)) {
          if (ident === normalizedSlug) {
            hasMatchingKey = true;
            weaponFlags[key] = true;
          } else {
            delete weaponFlags[key];
          }
        }
      });
      if (!hasMatchingKey) {
        const key = normalizedSlug || slugText.toLowerCase();
        weaponFlags[key] = true;
      }
    }
  }
  const unitTraits = [...new Set(flagsToAbilityList(weaponFlags))];
  const quality = Number.isFinite(Number(unitQuality)) ? Number(unitQuality) : 4;
  (Array.isArray(options) ? options : []).forEach((option) => {
    if (!option || option.id === undefined || option.id === null) {
      return;
    }
    const weaponId = Number(option.id);
    if (!Number.isFinite(weaponId)) {
      return;
    }
    const attacks = option.attacks ?? option.display_attacks ?? 0;
    const ap = option.ap ?? 0;
    const traits = splitTraits(option.traits);
    const cost = weaponCostInternal(quality, option.range, attacks, ap, traits, unitTraits, true);
    if (Number.isFinite(cost)) {
      const rounded = Math.max(0, Math.round(cost * 100) / 100);
      result.set(weaponId, rounded);
    }
  });
  return result;
}

function initNumberPicker(root) {
  const selectEl = root.querySelector('.number-picker-select');
  const customInput = root.querySelector('.number-picker-custom');
  const hiddenInput = root.querySelector('.number-picker-value');
  const initialValue = root.dataset.selected || '';

  const syncHidden = (value) => {
    const text = value !== undefined && value !== null ? String(value) : '';
    if (hiddenInput) {
      hiddenInput.value = text;
    }
    root.dataset.selected = text;
  };

  const hideCustom = () => {
    if (customInput) {
      customInput.classList.add('d-none');
      customInput.value = '';
    }
  };

  const showCustom = () => {
    if (customInput) {
      customInput.classList.remove('d-none');
    }
  };

  const findMatchingOption = (value) => {
    if (!selectEl) {
      return '';
    }
    const textValue = String(value).trim();
    if (!textValue) {
      return '';
    }
    const numeric = Number(textValue);
    let matched = '';
    Array.from(selectEl.options || []).forEach((option) => {
      if (!option.value || option.value === '__custom__') {
        if (!matched && option.value === textValue) {
          matched = option.value;
        }
        return;
      }
      if (option.value === textValue) {
        matched = option.value;
        return;
      }
      const optionNumeric = Number(option.value);
      if (Number.isFinite(optionNumeric) && Number.isFinite(numeric) && optionNumeric === numeric) {
        matched = option.value;
      }
    });
    return matched;
  };

  const setValue = (rawValue) => {
    const textValue = rawValue !== undefined && rawValue !== null ? String(rawValue).trim() : '';
    if (!textValue) {
      if (selectEl) {
        selectEl.value = '';
      }
      hideCustom();
      syncHidden('');
      return;
    }
    const matched = findMatchingOption(textValue);
    if (matched) {
      if (selectEl) {
        selectEl.value = matched;
      }
      hideCustom();
      syncHidden(matched);
      return;
    }
    if (selectEl) {
      selectEl.value = '__custom__';
    }
    showCustom();
    if (customInput) {
      customInput.value = textValue;
    }
    syncHidden(textValue);
  };

  if (selectEl) {
    selectEl.addEventListener('change', () => {
      const value = selectEl.value;
      if (value === '__custom__') {
        showCustom();
        if (customInput && !customInput.value) {
          customInput.focus();
        }
        syncHidden(customInput ? customInput.value || '' : '');
      } else if (value === '') {
        hideCustom();
        syncHidden('');
      } else {
        hideCustom();
        syncHidden(value);
      }
    });
  }

  if (customInput) {
    customInput.addEventListener('input', () => {
      if (selectEl && selectEl.value !== '__custom__') {
        selectEl.value = '__custom__';
      }
      syncHidden(customInput.value || '');
    });
  }

  setValue(initialValue);

  root.numberPicker = {
    setValue: (value) => setValue(value),
  };
}

function initNumberPickers() {
  document.querySelectorAll('[data-number-picker]').forEach((element) => {
    initNumberPicker(element);
  });
}

function initRangePicker(root) {
  const selectEl = root.querySelector('.range-picker-select');
  const customInput = root.querySelector('.range-picker-custom');
  const hiddenInput = root.querySelector('.range-picker-value');
  const initialValue = root.dataset.selected || '';

  const normalizeForOption = (raw) => {
    if (raw === undefined || raw === null) {
      return '';
    }
    const text = String(raw).trim();
    if (!text) {
      return '';
    }
    const lowered = text.toLowerCase();
    if (lowered === 'none' || lowered === 'null' || lowered === 'undefined') {
      return '';
    }
    if (['wręcz', 'wrecz', 'melee', 'm'].includes(lowered)) {
      return '0';
    }
    const numericMatch = lowered.match(/^(\d+)(?:["”])?$/);
    if (numericMatch) {
      return numericMatch[1];
    }
    return text;
  };

  const showCustom = () => {
    if (customInput) {
      customInput.classList.remove('d-none');
    }
  };

  const hideCustom = () => {
    if (customInput) {
      customInput.classList.add('d-none');
      customInput.value = '';
    }
  };

  const syncHidden = (value) => {
    const text = value !== undefined && value !== null ? String(value) : '';
    if (hiddenInput) {
      hiddenInput.value = text;
    }
    root.dataset.selected = text;
  };

  const setValue = (rawValue) => {
    const textValue = rawValue !== undefined && rawValue !== null ? String(rawValue).trim() : '';
    if (!textValue) {
      if (selectEl) {
        selectEl.value = '';
      }
      hideCustom();
      syncHidden('');
      return;
    }
    if (textValue.toLowerCase() === '__custom__') {
      if (selectEl) {
        selectEl.value = '__custom__';
      }
      showCustom();
      if (customInput && !customInput.value) {
        customInput.focus();
      }
      syncHidden(customInput ? customInput.value || '' : '');
      return;
    }
    const normalized = normalizeForOption(textValue);
    if (!normalized) {
      if (selectEl) {
        selectEl.value = '';
      }
      hideCustom();
      syncHidden('');
      return;
    }
    if (selectEl && normalized !== '__custom__') {
      const option = Array.from(selectEl.options || []).find((opt) => opt.value === normalized);
      if (option && normalized !== '__custom__') {
        selectEl.value = normalized;
        hideCustom();
        syncHidden(normalized);
        return;
      }
    }
    if (selectEl) {
      selectEl.value = '__custom__';
    }
    showCustom();
    if (customInput) {
      customInput.value = textValue;
    }
    syncHidden(textValue);
  };

  if (selectEl) {
    selectEl.addEventListener('change', () => {
      const value = selectEl.value;
      if (value === '__custom__') {
        showCustom();
        if (customInput && !customInput.value) {
          customInput.focus();
        }
        syncHidden(customInput ? customInput.value : '');
      } else {
        hideCustom();
        syncHidden(value);
      }
    });
  }

  if (customInput) {
    customInput.addEventListener('input', () => {
      syncHidden(customInput.value || '');
    });
  }

  setValue(initialValue);
  root.rangePicker = {
    setValue,
  };
}

function initRangePickers() {
  document.querySelectorAll('[data-range-picker]').forEach((element) => {
    initRangePicker(element);
  });
}

function initWeaponDefaults() {
  document.querySelectorAll('form[data-defaults]').forEach((form) => {
    const defaultsData = form.dataset.defaults;
    if (!defaultsData) {
      return;
    }
    let defaults = null;
    try {
      defaults = JSON.parse(defaultsData);
    } catch (err) {
      defaults = null;
    }
    if (!defaults) {
      return;
    }
    const resetButton = form.querySelector('[data-weapon-reset]');
    if (!resetButton) {
      return;
    }
    resetButton.addEventListener('click', () => {
      const nameInput = form.querySelector('#name');
      if (nameInput) {
        nameInput.value = defaults.name || '';
      }
      const rangePicker = form.querySelector('[data-range-picker]');
      if (rangePicker && rangePicker.rangePicker && typeof rangePicker.rangePicker.setValue === 'function') {
        rangePicker.rangePicker.setValue(defaults.range || '');
      }
      const attacksPicker = form.querySelector('[data-number-picker][data-target-input="attacks"]');
      if (attacksPicker && attacksPicker.numberPicker && typeof attacksPicker.numberPicker.setValue === 'function') {
        attacksPicker.numberPicker.setValue(defaults.attacks || '');
      } else {
        const attacksInput = form.querySelector('#attacks');
        if (attacksInput) {
          attacksInput.value = defaults.attacks || '';
        }
      }
      const apPicker = form.querySelector('[data-number-picker][data-target-input="ap"]');
      if (apPicker && apPicker.numberPicker && typeof apPicker.numberPicker.setValue === 'function') {
        apPicker.numberPicker.setValue(defaults.ap || '');
      } else {
        const apInput = form.querySelector('#ap');
        if (apInput) {
          apInput.value = defaults.ap || '';
        }
      }
      const notesInput = form.querySelector('#notes');
      if (notesInput) {
        notesInput.value = defaults.notes || '';
      }
      const abilityPickerRoot = form.querySelector('[data-ability-picker]');
      if (abilityPickerRoot && abilityPickerRoot.abilityPicker && typeof abilityPickerRoot.abilityPicker.setItems === 'function') {
        abilityPickerRoot.abilityPicker.setItems(defaults.abilities || []);
      }
    });
  });
}

function initWeaponPicker(root) {
  const treePayloadRaw =
    root.dataset.weaponTreePayload ||
    root.dataset.weaponTree ||
    root.dataset.weapons;
  let parsedPayload = null;
  if (treePayloadRaw) {
    try {
      parsedPayload = JSON.parse(treePayloadRaw);
    } catch (err) {
      console.warn('Nie udało się odczytać drzewa uzbrojenia', err);
      parsedPayload = null;
    }
  }

  let rawTree = [];
  let rawFlat = [];
  if (Array.isArray(parsedPayload)) {
    rawTree = parsedPayload;
  } else if (parsedPayload && typeof parsedPayload === 'object') {
    if (Array.isArray(parsedPayload.tree)) {
      rawTree = parsedPayload.tree;
    } else if (Array.isArray(parsedPayload.nodes)) {
      rawTree = parsedPayload.nodes;
    }
    if (Array.isArray(parsedPayload.flat)) {
      rawFlat = parsedPayload.flat;
    }
  }

  if ((!Array.isArray(rawTree) || !rawTree.length) && Array.isArray(rawFlat) && rawFlat.length) {
    const cloneMap = new Map();
    rawFlat.forEach((entry) => {
      if (!entry || typeof entry !== 'object') {
        return;
      }
      const id = Number.parseInt(entry.id ?? entry.weapon_id, 10);
      if (!Number.isFinite(id)) {
        return;
      }
      cloneMap.set(String(id), {
        id,
        name: typeof entry.name === 'string' ? entry.name : '',
        parent_id:
          entry.parent_id !== undefined && entry.parent_id !== null
            ? Number(entry.parent_id)
            : null,
        range_value: entry.range_value,
        category: entry.category,
        children: [],
        path: entry.path,
        path_labels: entry.path_labels,
        path_text: entry.path_text,
        is_leaf: entry.is_leaf,
      });
    });
    const roots = [];
    cloneMap.forEach((node) => {
      const parentId =
        node.parent_id !== undefined && node.parent_id !== null
          ? Number(node.parent_id)
          : null;
      if (Number.isFinite(parentId) && cloneMap.has(String(parentId))) {
        cloneMap.get(String(parentId)).children.push(node);
      } else {
        roots.push(node);
      }
    });
    rawTree = roots;
  }

  const targetId = root.dataset.targetInput;
  const hiddenInput =
    targetId ? document.getElementById(targetId) : root.querySelector('input[type="hidden"]');
  const selectEl = root.querySelector('.weapon-picker-select');
  const defaultCountInput = root.querySelector('.weapon-picker-default-count');
  const addButton = root.querySelector('.weapon-picker-add');
  const listEl = root.querySelector('.weapon-picker-list');
  const treeRoot = root.querySelector('[data-weapon-tree]');
  if (treeRoot) {
    treeRoot.setAttribute('tabindex', '-1');
  }
  const pickerId = Math.random().toString(16).slice(2);

  const treeContainer = root.querySelector('[data-weapon-tree-container]');
  const treeTrigger = root.querySelector('[data-weapon-tree-trigger]');
  const treeTriggerLabel = root.querySelector('[data-weapon-tree-label]');
  const treePlaceholder =
    (treeTrigger && treeTrigger.dataset.weaponTreePlaceholder) ||
    (treeTriggerLabel && treeTriggerLabel.textContent?.trim()) ||
    (treeTrigger && treeTrigger.textContent?.trim()) ||
    'Wybierz broń';
  const treeContainerId =
    treeContainer && (treeContainer.id || `weapon-tree-container-${pickerId}`);
  if (treeContainer && !treeContainer.id && treeContainerId) {
    treeContainer.id = treeContainerId;
  }
  if (treeTrigger && treeContainerId) {
    treeTrigger.setAttribute('aria-controls', treeContainerId);
  }
  if (treeTrigger) {
    treeTrigger.dataset.weaponTreePlaceholder = treePlaceholder;
  }
  if (treeTriggerLabel) {
    treeTriggerLabel.dataset.weaponTreePlaceholder = treePlaceholder;
  }

  let treeExpanded = !treeTrigger;
  let outsidePointerAttached = false;

  function handleOutsidePointer(event) {
    if (!treeExpanded || !treeTrigger || !treeContainer) {
      return;
    }
    const target = event.target;
    if (!(target instanceof Node)) {
      return;
    }
    if (treeExpanded) {
      const safeElements = [treeContainer];
      const caret = root.querySelector('.weapon-picker-tree-trigger-caret');
      if (caret && !safeElements.includes(caret)) {
        safeElements.push(caret);
      }
      const isInsideTree = safeElements.some(
        (element) => element instanceof Node && element.contains(target),
      );
      if (isInsideTree) {
        return;
      }

      treeExpanded = false;
      syncTreeVisibility();
      if (typeof treeTrigger.focus === 'function') {
        treeTrigger.focus();
      }
    }
  }

  function syncTreeVisibility() {
    if (!treeContainer || !treeTrigger) {
      treeExpanded = true;
      if (outsidePointerAttached) {
        document.removeEventListener('pointerdown', handleOutsidePointer, true);
        outsidePointerAttached = false;
      }
      if (treeRoot) {
        treeRoot.setAttribute('aria-hidden', 'false');
      }
      return;
    }
    const expanded = Boolean(treeExpanded);
    if (expanded) {
      if (!outsidePointerAttached) {
        document.addEventListener('pointerdown', handleOutsidePointer, true);
        outsidePointerAttached = true;
      }
    } else if (outsidePointerAttached) {
      document.removeEventListener('pointerdown', handleOutsidePointer, true);
      outsidePointerAttached = false;
    }
    treeContainer.hidden = !expanded;
    treeContainer.classList.toggle('d-none', !expanded);
    treeContainer.classList.toggle('weapon-tree-container-open', expanded);
    treeTrigger.hidden = expanded;
    treeTrigger.classList.toggle('d-none', expanded);
    treeTrigger.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    treeTrigger.classList.toggle('weapon-tree-trigger-open', expanded);
    if (treeRoot) {
      treeRoot.setAttribute('aria-hidden', expanded ? 'false' : 'true');
    }
  }

  syncTreeVisibility();

  if (treeTrigger && treeContainer) {
    treeTrigger.addEventListener('click', (event) => {
      event.preventDefault();
      treeExpanded = !treeExpanded;
      syncTreeVisibility();
      if (treeExpanded && treeRoot && typeof treeRoot.focus === 'function') {
        treeRoot.focus();
      }
    });
  }

  if (treeRoot && treeTrigger && treeContainer) {
    treeRoot.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        treeExpanded = false;
        syncTreeVisibility();
        if (typeof treeTrigger.focus === 'function') {
          treeTrigger.focus();
        }
      }
    });
  }

  const weaponMap = new Map();
  const collapsedNodes = new Set();
  let treeData = [];
  let items = [];
  let selectedWeaponId = null;

  function normalizeCategory(value) {
    if (typeof value !== 'string') {
      return null;
    }
    const lowered = value.trim().toLowerCase();
    if (
      [
        'ranged',
        'dystansowa',
        'dystansowe',
        'dystansowy',
        'shooting',
        'shoot',
        'range',
      ].includes(lowered)
    ) {
      return 'ranged';
    }
    if (['melee', 'wręcz', 'wrecz', 'close', 'close combat'].includes(lowered)) {
      return 'melee';
    }
    return null;
  }

  function sanitizeTree(nodes, parentId = null, parentPathIds = [], parentPathLabels = []) {
    const result = [];
    (Array.isArray(nodes) ? nodes : []).forEach((node) => {
      if (!node || typeof node !== 'object') {
        return;
      }
      const rawId = node.id ?? node.weapon_id;
      const id = Number.parseInt(rawId, 10);
      if (!Number.isFinite(id)) {
        return;
      }
      const rawName = typeof node.name === 'string' ? node.name : '';
      const name = rawName.trim() || `Broń #${id}`;
      let pathIds = Array.isArray(node.path)
        ? node.path
            .map((value) => Number.parseInt(value, 10))
            .filter((value) => Number.isFinite(value))
        : [];
      if (!pathIds.length || pathIds[pathIds.length - 1] !== id) {
        pathIds = [...parentPathIds, id];
      }
      let pathLabels = Array.isArray(node.path_labels)
        ? node.path_labels.map((value) => String(value))
        : [];
      if (!pathLabels.length || pathLabels.length !== pathIds.length) {
        pathLabels = [...parentPathLabels, name];
      }
      const depth = pathIds.length ? pathIds.length - 1 : parentPathIds.length;
      const rangeSource =
        node.range_value ??
        node.range ??
        node.effective_range ??
        node.rangeValue ??
        0;
      const rangeValue = normalizeRangeValue(rangeSource);
      const rawCategory =
        node.category ?? node.range_category ?? node.type ?? null;
      const category =
        normalizeCategory(rawCategory) ?? (rangeValue > 0 ? 'ranged' : 'melee');
      let parentValue = null;
      if (Number.isFinite(Number(node.parent_id))) {
        parentValue = Number(node.parent_id);
      } else if (pathIds.length >= 2) {
        parentValue = pathIds[pathIds.length - 2];
      } else if (Number.isFinite(Number(parentId))) {
        parentValue = Number(parentId);
      }
      const childNodes = sanitizeTree(
        node.children,
        id,
        pathIds,
        pathLabels,
      );
      const hasChildren = childNodes.length > 0;
      const isLeaf = !hasChildren || Boolean(node.is_leaf);
      const meta = {
        id,
        name,
        parent_id: Number.isFinite(parentValue) ? parentValue : null,
        depth,
        path: pathIds,
        path_labels: pathLabels,
        path_text:
          typeof node.path_text === 'string' && node.path_text.trim()
            ? node.path_text.trim()
            : pathLabels.join(' / '),
        category,
        range_value: Number.isFinite(rangeValue) ? rangeValue : 0,
        is_leaf: isLeaf,
      };
      weaponMap.set(String(id), { ...meta });
      const sanitizedNode = {
        ...meta,
        children: childNodes,
        has_children: hasChildren,
      };
      result.push(sanitizedNode);
    });
    return result;
  }

  function sortTree(nodes) {
    if (!Array.isArray(nodes)) {
      return;
    }
    nodes.sort((a, b) => {
      const nameA = a && a.name ? String(a.name).toLowerCase() : '';
      const nameB = b && b.name ? String(b.name).toLowerCase() : '';
      if (nameA < nameB) {
        return -1;
      }
      if (nameA > nameB) {
        return 1;
      }
      return 0;
    });
    nodes.forEach((node) => {
      if (node && Array.isArray(node.children) && node.children.length) {
        sortTree(node.children);
      }
    });
  }

  treeData = sanitizeTree(rawTree);
  sortTree(treeData);

  if (Array.isArray(rawFlat)) {
    rawFlat.forEach((entry) => {
      if (!entry || typeof entry !== 'object') {
        return;
      }
      const id = Number.parseInt(entry.id ?? entry.weapon_id, 10);
      if (!Number.isFinite(id) || weaponMap.has(String(id))) {
        return;
      }
      const rawName = typeof entry.name === 'string' ? entry.name : '';
      const name = rawName.trim() || `Broń #${id}`;
      const rangeValue = normalizeRangeValue(
        entry.range_value ?? entry.range ?? entry.effective_range ?? 0,
      );
      const category =
        normalizeCategory(entry.category ?? entry.range_category ?? null) ??
        (rangeValue > 0 ? 'ranged' : 'melee');
      let path = Array.isArray(entry.path)
        ? entry.path
            .map((value) => Number.parseInt(value, 10))
            .filter((value) => Number.isFinite(value))
        : [];
      if (!path.length || path[path.length - 1] !== id) {
        path = [...path, id];
      }
      let pathLabels = Array.isArray(entry.path_labels)
        ? entry.path_labels.map((value) => String(value))
        : [];
      if (!pathLabels.length || pathLabels.length !== path.length) {
        pathLabels = path.map((value, index) => {
          if (index === path.length - 1) {
            return name;
          }
          const ancestor = weaponMap.get(String(path[index]));
          return ancestor && ancestor.name ? ancestor.name : `#${path[index]}`;
        });
      }
      weaponMap.set(String(id), {
        id,
        name,
        parent_id:
          entry.parent_id !== undefined && entry.parent_id !== null
            ? Number(entry.parent_id)
            : path.length > 1
            ? path[path.length - 2]
            : null,
        depth: Number.isFinite(Number(entry.depth))
          ? Number(entry.depth)
          : Math.max(path.length - 1, 0),
        path,
        path_labels: pathLabels,
        path_text:
          typeof entry.path_text === 'string' && entry.path_text.trim()
            ? entry.path_text.trim()
            : pathLabels.join(' / '),
        category,
        range_value: Number.isFinite(rangeValue) ? rangeValue : 0,
        is_leaf: entry.is_leaf !== undefined ? Boolean(entry.is_leaf) : true,
      });
    });
  }

  function initializeCollapsedState(nodes) {
    (Array.isArray(nodes) ? nodes : []).forEach((node) => {
      if (!node) {
        return;
      }
      if (node.has_children) {
        collapsedNodes.add(String(node.id));
      }
      initializeCollapsedState(node.children);
    });
  }

  initializeCollapsedState(treeData);

  function ensureNodeVisible(weaponId) {
    const meta = weaponMap.get(String(weaponId));
    if (!meta || !Array.isArray(meta.path)) {
      return;
    }
    meta.path.slice(0, -1).forEach((ancestorId) => {
      collapsedNodes.delete(String(ancestorId));
    });
  }

  function toggleNode(nodeId, forceOpen) {
    const key = String(nodeId);
    if (forceOpen === true) {
      collapsedNodes.delete(key);
    } else if (forceOpen === false) {
      collapsedNodes.add(key);
    } else if (collapsedNodes.has(key)) {
      collapsedNodes.delete(key);
    } else {
      collapsedNodes.add(key);
    }
    renderTree();
    updateSelectionState();
  }

  function createNodeElement(node) {
    const li = document.createElement('li');
    li.className = 'weapon-tree-node';
    li.dataset.weaponNode = String(node.id);

    const row = document.createElement('div');
    row.className = 'weapon-tree-row d-flex align-items-center gap-2 py-1';
    li.appendChild(row);

    if (node.has_children) {
      const toggleBtn = document.createElement('button');
      toggleBtn.type = 'button';
      toggleBtn.className = 'btn btn-sm btn-outline-secondary weapon-tree-toggle';
      const collapsed = collapsedNodes.has(String(node.id));
      toggleBtn.textContent = collapsed ? '▸' : '▾';
      toggleBtn.setAttribute('aria-label', collapsed ? 'Rozwiń gałąź' : 'Zwiń gałąź');
      toggleBtn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      toggleBtn.addEventListener('click', (event) => {
        event.preventDefault();
        toggleNode(node.id);
      });
      row.appendChild(toggleBtn);
    } else {
      const spacer = document.createElement('span');
      spacer.className = 'weapon-tree-toggle-placeholder';
      spacer.style.display = 'inline-block';
      spacer.style.width = '1.75rem';
      spacer.setAttribute('aria-hidden', 'true');
      row.appendChild(spacer);
    }

    if (node.is_leaf) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className =
        'btn btn-sm btn-outline-secondary weapon-tree-select flex-grow-1 text-start';
      button.dataset.weaponSelect = String(node.id);
      button.textContent = node.name;
      button.title = node.path_text || node.name;
      button.addEventListener('click', (event) => {
        event.preventDefault();
        setSelectedNode(node.id);
      });
      button.addEventListener('dblclick', (event) => {
        event.preventDefault();
        setSelectedNode(node.id);
        handleAdd();
      });
      row.appendChild(button);
    } else {
      const label = document.createElement('button');
      label.type = 'button';
      label.className =
        'btn btn-sm btn-outline-secondary weapon-tree-group flex-grow-1 text-start';
      label.dataset.weaponSelect = String(node.id);
      label.textContent = node.name;
      label.title = node.path_text || node.name;
      label.addEventListener('click', (event) => {
        event.preventDefault();
        setSelectedNode(node.id, { allowGroup: true });
      });
      label.addEventListener('dblclick', (event) => {
        event.preventDefault();
        setSelectedNode(node.id, { allowGroup: true });
        handleAdd();
      });
      row.appendChild(label);
    }

    const badge = document.createElement('span');
    if (node.is_leaf) {
      badge.className = 'badge text-bg-secondary weapon-tree-meta';
      badge.textContent = node.range_value > 0 ? `${node.range_value}"` : 'Wręcz';
    } else {
      badge.className = 'badge text-bg-light border text-muted weapon-tree-meta';
      badge.textContent = `${node.children.length}`;
      badge.title = 'Liczba wariantów';
    }
    row.appendChild(badge);

    if (node.children && node.children.length) {
      const childList = document.createElement('ul');
      childList.className = 'list-unstyled mb-0 weapon-tree-children ms-3';
      if (collapsedNodes.has(String(node.id))) {
        childList.hidden = true;
      }
      node.children.forEach((child) => {
        childList.appendChild(createNodeElement(child));
      });
      li.appendChild(childList);
    }

    return li;
  }

  function renderTree() {
    if (!treeRoot) {
      return;
    }
    treeRoot.innerHTML = '';
    treeRoot.classList.add('d-flex', 'flex-column', 'gap-2');
    treeRoot.setAttribute('role', 'tree');

    if (!Array.isArray(treeData) || !treeData.length) {
      const empty = document.createElement('p');
      empty.className = 'text-muted mb-0 fst-italic small';
      empty.textContent = 'Brak dostępnego uzbrojenia.';
      treeRoot.appendChild(empty);
      return;
    }

    const list = document.createElement('ul');
    list.className = 'list-unstyled mb-0 weapon-tree-root';
    treeData.forEach((node) => {
      list.appendChild(createNodeElement(node));
    });
    treeRoot.appendChild(list);
  }

  function updateTriggerLabel() {
    if (!treeTrigger) {
      return;
    }
    const labelElement = treeTriggerLabel || treeTrigger;
    const placeholder =
      treeTrigger.dataset.weaponTreePlaceholder ||
      treeTriggerLabel?.dataset.weaponTreePlaceholder ||
      treePlaceholder;
    let labelText = placeholder;
    let titleText = placeholder || '';
    if (selectedWeaponId) {
      const meta = getWeaponMeta(selectedWeaponId);
      if (meta) {
        labelText = meta.name || placeholder;
        titleText = meta.pathText || meta.name || labelText;
      }
    }
    if (labelElement) {
      labelElement.textContent = labelText;
    }
    if (titleText) {
      treeTrigger.title = titleText;
    } else {
      treeTrigger.removeAttribute('title');
    }
  }

  function updateSelectionState() {
    if (addButton) {
      if (treeRoot) {
        addButton.disabled = !selectedWeaponId;
      } else {
        addButton.disabled = false;
      }
    }
    updateTriggerLabel();
    if (!treeRoot) {
      return;
    }
    treeRoot.querySelectorAll('[data-weapon-select]').forEach((button) => {
      const nodeId = button.dataset.weaponSelect;
      const isSelected = selectedWeaponId && nodeId === selectedWeaponId;
      button.classList.toggle('btn-primary', Boolean(isSelected));
      button.classList.toggle('btn-outline-secondary', !isSelected);
      const nodeElement = button.closest('[data-weapon-node]');
      if (nodeElement) {
        nodeElement.classList.toggle('active', Boolean(isSelected));
      }
    });
  }

  function setSelectedNode(weaponId, options = {}) {
    const key = String(weaponId ?? '');
    if (!key) {
      selectedWeaponId = null;
      updateSelectionState();
      return;
    }
    const meta = weaponMap.get(key);
    if (!meta) {
      return;
    }
    const allowGroup = Boolean(options && options.allowGroup);
    if (!meta.is_leaf && !allowGroup) {
      return;
    }
    selectedWeaponId = key;
    ensureNodeVisible(meta.id);
    if (selectEl) {
      selectEl.value = key;
    }
    renderTree();
    updateSelectionState();
    if (treeTrigger && treeContainer && treeExpanded) {
      treeExpanded = false;
      syncTreeVisibility();
      if (typeof treeTrigger.focus === 'function') {
        treeTrigger.focus();
      }
    }
  }

  function getWeaponMeta(weaponId, entry) {
    const idKey =
      weaponId !== undefined && weaponId !== null ? weaponId : entry ? entry.weapon_id : undefined;
    const meta = idKey !== undefined && idKey !== null ? weaponMap.get(String(idKey)) : undefined;
    const rangeSource =
      (entry && entry.range_value !== undefined ? entry.range_value : undefined) ??
      (entry && entry.range !== undefined ? entry.range : undefined) ??
      (meta && meta.range_value !== undefined ? meta.range_value : undefined) ??
      0;
    const rangeValue = normalizeRangeValue(rangeSource);
    const categorySource =
      (entry && entry.category !== undefined && entry.category !== null ? entry.category : null) ??
      (meta ? meta.category : null);
    const category =
      normalizeCategory(categorySource) ?? (Number.isFinite(rangeValue) && rangeValue > 0 ? 'ranged' : 'melee');
    const pathText = meta && meta.path_text ? meta.path_text : '';
    const pathLabels = meta && Array.isArray(meta.path_labels) ? [...meta.path_labels] : [];
    const path = meta && Array.isArray(meta.path) ? [...meta.path] : [];
    const name =
      (meta && meta.name) ||
      (entry && entry.name) ||
      (selectEl && idKey !== undefined && idKey !== null
        ? selectEl.querySelector(`option[value="${String(idKey)}"]`)?.textContent
        : null) ||
      (idKey !== undefined && idKey !== null ? `Broń #${idKey}` : 'Broń');
    return {
      category,
      rangeValue: Number.isFinite(rangeValue) ? rangeValue : 0,
      pathText,
      pathLabels,
      path,
      name,
      isLeaf: Boolean(meta && meta.is_leaf),
    };
  }

  function parsePrimaryFlag(value) {
    if (typeof value === 'boolean') {
      return value;
    }
    if (typeof value === 'number') {
      return Number.isFinite(value) ? value !== 0 : false;
    }
    if (typeof value === 'string') {
      return ['1', 'true', 'on', 'yes'].includes(value.trim().toLowerCase());
    }
    return false;
  }

  function parseInitial() {
    if (!hiddenInput || !hiddenInput.value) {
      items = [];
      return;
    }
    try {
      const parsed = JSON.parse(hiddenInput.value);
      if (!Array.isArray(parsed)) {
        items = [];
        return;
      }
      items = parsed
        .map((entry) => {
          if (!entry) {
            return null;
          }
          const rawWeaponId = entry.weapon_id ?? entry.weaponId ?? entry.id;
          const weaponId = Number.parseInt(rawWeaponId, 10);
          if (!Number.isFinite(weaponId)) {
            return null;
          }
          const meta = getWeaponMeta(weaponId, entry);
          const name =
            entry.name ||
            meta.name ||
            weaponMap.get(String(weaponId))?.name ||
            `Broń #${weaponId}`;
          const rawCount = entry.count ?? entry.default_count ?? entry.quantity;
          let defaultCount = Number.parseInt(rawCount, 10);
          if (!Number.isFinite(defaultCount)) {
            defaultCount = parsePrimaryFlag(entry.is_default) ? 1 : 0;
          }
          if (defaultCount < 0) {
            defaultCount = 0;
          }
          const primaryFlag = parsePrimaryFlag(
            entry.is_primary ?? entry.primary ?? entry.is_primary_weapon,
          );
          return {
            weapon_id: weaponId,
            name,
            default_count: defaultCount,
            is_primary: primaryFlag && defaultCount > 0,
            category: meta.category,
            range_value: meta.rangeValue,
            path_text: meta.pathText,
            path: meta.path,
            path_labels: meta.pathLabels,
          };
        })
        .filter((entry) => entry && entry.weapon_id);
    } catch (err) {
      console.warn('Nie udało się odczytać listy broni', err);
      items = [];
    }
  }

  function updateHidden() {
    if (hiddenInput) {
      const payload = items.map((entry) => ({
        weapon_id: entry.weapon_id,
        name: entry.name,
        is_default: entry.default_count > 0,
        is_primary: Boolean(entry.is_primary && Number(entry.default_count) > 0),
        count: entry.default_count,
        default_count: entry.default_count,
        category: entry.category,
        range_value: entry.range_value,
      }));
      hiddenInput.value = JSON.stringify(payload);
    }
  }

  function moveItem(fromIndex, toIndex) {
    if (!Array.isArray(items)) {
      return;
    }
    const lastIndex = items.length - 1;
    if (
      fromIndex === toIndex ||
      fromIndex < 0 ||
      toIndex < 0 ||
      fromIndex > lastIndex ||
      toIndex > lastIndex
    ) {
      return;
    }
    const [entry] = items.splice(fromIndex, 1);
    items.splice(toIndex, 0, entry);
    updateHidden();
    renderList();
  }

  function ensureUnique(weaponId) {
    return !items.some((entry) => String(entry.weapon_id) === String(weaponId));
  }

  function sanitizePrimaryFlags() {
    if (!Array.isArray(items)) {
      items = [];
      return false;
    }
    if (!items.length) {
      return false;
    }
    let changed = false;
    items.forEach((entry) => {
      if (!entry) {
        return;
      }
      const countValue = Number(entry.default_count);
      const safeCount = Number.isFinite(countValue) ? countValue : 0;
      const shouldBePrimary = safeCount > 0 ? Boolean(entry.is_primary) : false;
      if (entry.is_primary !== shouldBePrimary) {
        entry.is_primary = shouldBePrimary;
        changed = true;
      }
    });
    return changed;
  }

  function renderList() {
    if (!listEl) {
      return;
    }
    listEl.innerHTML = '';
    if (!items.length) {
      const empty = document.createElement('p');
      empty.className = 'text-muted mb-0';
      empty.textContent = 'Nie wybrano jeszcze żadnej broni.';
      listEl.appendChild(empty);
      return;
    }
    const wrapper = document.createElement('div');
    wrapper.className = 'd-flex flex-column gap-2';
    items.forEach((item, index) => {
      const row = document.createElement('div');
      row.className = 'border rounded p-2 d-flex flex-wrap align-items-center gap-2';

      const nameWrapper = document.createElement('div');
      nameWrapper.className = 'flex-grow-1 d-flex flex-column';

      const nameRow = document.createElement('div');
      nameRow.className = 'd-flex flex-wrap align-items-center gap-2';

      const nameLabel = document.createElement('span');
      nameLabel.className = 'fw-semibold';
      nameLabel.textContent =
        item.name || weaponMap.get(String(item.weapon_id))?.name || `Broń #${item.weapon_id}`;
      nameRow.appendChild(nameLabel);

      const rangeBadge = document.createElement('span');
      rangeBadge.className = 'badge text-bg-secondary';
      rangeBadge.textContent = Number(item.range_value) > 0 ? `${item.range_value}"` : 'Wręcz';
      nameRow.appendChild(rangeBadge);

      nameWrapper.appendChild(nameRow);

      const pathText =
        item.path_text ||
        weaponMap.get(String(item.weapon_id))?.path_text ||
        '';
      if (pathText && pathText !== nameLabel.textContent) {
        const pathInfo = document.createElement('span');
        pathInfo.className = 'text-muted small';
        pathInfo.textContent = pathText;
        nameWrapper.appendChild(pathInfo);
      }

      const defaultGroup = document.createElement('div');
      defaultGroup.className = 'd-flex align-items-center gap-2 weapon-default-group';
      const defaultLabel = document.createElement('label');
      defaultLabel.className = 'form-label mb-0 small text-nowrap';
      defaultLabel.textContent = 'Domyślnie:';
      defaultLabel.setAttribute('for', `weapon-default-count-${item.weapon_id}-${index}`);
      const defaultField = document.createElement('input');
      defaultField.className = 'form-control form-control-sm weapon-default-count-input';
      defaultField.type = 'number';
      defaultField.min = '0';
      defaultField.value = Number.isFinite(item.default_count) ? item.default_count : 0;
      defaultField.id = `weapon-default-count-${item.weapon_id}-${index}`;
      defaultField.addEventListener('change', () => {
        const parsed = Number.parseInt(defaultField.value, 10);
        const safeValue = Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
        defaultField.value = safeValue;
        if (items[index]) {
          items[index].default_count = safeValue;
        }
        sanitizePrimaryFlags();
        updateHidden();
        renderList();
      });
      defaultGroup.appendChild(defaultLabel);
      defaultGroup.appendChild(defaultField);

      const primaryWrapper = document.createElement('div');
      primaryWrapper.className = 'form-check mb-0 d-flex align-items-center gap-2';
      const primaryInput = document.createElement('input');
      primaryInput.type = 'checkbox';
      primaryInput.className = 'form-check-input';
      const primaryId = `weapon-primary-${pickerId}-${item.weapon_id}-${index}`;
      primaryInput.id = primaryId;
      const hasDefault = Number(item.default_count) > 0;
      primaryInput.checked = Boolean(item.is_primary) && hasDefault;
      primaryInput.disabled = !hasDefault;
      primaryInput.addEventListener('change', () => {
        if (!items[index]) {
          return;
        }
        items[index].is_primary = Boolean(primaryInput.checked);
        const changed = sanitizePrimaryFlags();
        updateHidden();
        if (changed) {
          renderList();
        }
      });
      const primaryLabel = document.createElement('label');
      primaryLabel.className = 'form-check-label small';
      primaryLabel.setAttribute('for', primaryId);
      primaryLabel.textContent = 'Podstawowa';
      primaryWrapper.appendChild(primaryInput);
      primaryWrapper.appendChild(primaryLabel);

      row.appendChild(nameWrapper);
      row.appendChild(defaultGroup);
      row.appendChild(primaryWrapper);

      const actionsWrapper = document.createElement('div');
      actionsWrapper.className = 'd-flex flex-column flex-sm-row gap-2';

      const reorderGroup = document.createElement('div');
      reorderGroup.className = 'btn-group-vertical';
      const moveUpBtn = document.createElement('button');
      moveUpBtn.type = 'button';
      moveUpBtn.className = 'btn btn-outline-secondary btn-sm';
      moveUpBtn.textContent = '↑';
      moveUpBtn.setAttribute('aria-label', 'Przesuń w górę');
      moveUpBtn.disabled = index === 0;
      moveUpBtn.addEventListener('click', (event) => {
        event.preventDefault();
        moveItem(index, index - 1);
      });
      const moveDownBtn = document.createElement('button');
      moveDownBtn.type = 'button';
      moveDownBtn.className = 'btn btn-outline-secondary btn-sm';
      moveDownBtn.textContent = '↓';
      moveDownBtn.setAttribute('aria-label', 'Przesuń w dół');
      moveDownBtn.disabled = index === items.length - 1;
      moveDownBtn.addEventListener('click', (event) => {
        event.preventDefault();
        moveItem(index, index + 1);
      });
      reorderGroup.appendChild(moveUpBtn);
      reorderGroup.appendChild(moveDownBtn);
      actionsWrapper.appendChild(reorderGroup);

      const removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'btn btn-outline-danger btn-sm';
      removeBtn.textContent = 'Usuń';
      removeBtn.addEventListener('click', () => {
        items.splice(index, 1);
        updateHidden();
        renderList();
      });
      actionsWrapper.appendChild(removeBtn);

      row.appendChild(actionsWrapper);
      wrapper.appendChild(row);
    });
    listEl.appendChild(wrapper);
  }

  function handleAdd() {
    const selectedId = selectedWeaponId || (selectEl ? selectEl.value : '');
    if (!selectedId) {
      return;
    }
    if (!ensureUnique(selectedId)) {
      if (selectEl) {
        selectEl.value = '';
      }
      selectedWeaponId = null;
      updateSelectionState();
      return;
    }
    const meta = getWeaponMeta(selectedId);
    const rawCount = defaultCountInput ? Number.parseInt(defaultCountInput.value, 10) : 0;
    const safeCount = Number.isFinite(rawCount) && rawCount >= 0 ? rawCount : 0;
    items.push({
      weapon_id: Number.parseInt(selectedId, 10),
      name: meta.name,
      default_count: safeCount,
      is_primary: false,
      category: meta.category,
      range_value: meta.rangeValue,
      path_text: meta.pathText,
      path: meta.path,
      path_labels: meta.pathLabels,
    });
    sanitizePrimaryFlags();
    updateHidden();
    renderList();
    selectedWeaponId = null;
    if (selectEl) {
      selectEl.value = '';
    }
    if (defaultCountInput) {
      defaultCountInput.value = '0';
    }
    updateSelectionState();
  }

  if (addButton) {
    addButton.addEventListener('click', handleAdd);
  }

  if (selectEl && !treeRoot) {
    selectEl.addEventListener('change', () => {
      const value = selectEl.value;
      selectedWeaponId = value || null;
      updateSelectionState();
    });
  }

  parseInitial();
  if (Array.isArray(items)) {
    items.forEach((entry) => {
      if (entry && entry.weapon_id !== undefined && entry.weapon_id !== null) {
        ensureNodeVisible(entry.weapon_id);
      }
    });
  }
  renderTree();
  sanitizePrimaryFlags();
  updateHidden();
  renderList();
  updateSelectionState();
}


function initWeaponPickers() {
  document.querySelectorAll('[data-weapon-picker]').forEach((element) => {
    initWeaponPicker(element);
  });
}

function formatPoints(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return value !== undefined && value !== null ? String(value) : '0';
  }
  const baseOptions = { minimumFractionDigits: 0, maximumFractionDigits: 2 };
  if (!Number.isInteger(number)) {
    baseOptions.minimumFractionDigits = 2;
  }
  return number.toLocaleString('pl-PL', baseOptions);
}

function createRosterItemElement(data, options = {}) {
  if (!data || typeof data !== 'object') {
    return null;
  }
  const { rosterId = '', isEditable = false } = options || {};
  const itemId = data.id !== undefined && data.id !== null ? String(data.id) : '';
  const count = Number.isFinite(Number(data.count)) ? Number(data.count) : 1;
  const cachedCost = Number.isFinite(Number(data.cached_cost)) ? Number(data.cached_cost) : 0;
  const unitName = data.unit_name || 'Jednostka';
  const unitQuality = data.unit_quality !== undefined ? data.unit_quality : '-';
  const unitDefense = data.unit_defense !== undefined ? data.unit_defense : '-';
  const unitToughness = data.unit_toughness !== undefined ? data.unit_toughness : '-';
  const defaultSummary = data.default_summary || '';
  const loadoutSummary = data.loadout_summary || defaultSummary;
  const customName = typeof data.custom_name === 'string' ? data.custom_name : '';
  const baseCostPerModel = Number.isFinite(Number(data.base_cost_per_model))
    ? Number(data.base_cost_per_model)
    : 0;
  const toJsonString = (value, fallback) => {
    const base = value === undefined ? fallback : value;
    try {
      return JSON.stringify(base);
    } catch (err) {
      try {
        return JSON.stringify(fallback);
      } catch (innerErr) {
        if (Array.isArray(fallback)) {
          return '[]';
        }
        if (fallback && typeof fallback === 'object') {
          return '{}';
        }
        return 'null';
      }
    }
  };

  const outer = document.createElement('div');
  outer.className = 'list-group-item border-0 px-0 py-2';

  const entry = document.createElement('div');
  entry.className = 'roster-unit-entry';
  outer.appendChild(entry);

  if (isEditable) {
    const reorder = document.createElement('div');
    reorder.className = 'roster-unit-reorder';
    entry.appendChild(reorder);

    ['up', 'down'].forEach((direction) => {
      const form = document.createElement('form');
      form.method = 'post';
      if (rosterId) {
        form.action = `/rosters/${rosterId}/units/${itemId || ''}/move`;
      }
      form.setAttribute('data-roster-move-form', '');

      const hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.name = 'direction';
      hidden.value = direction;
      form.appendChild(hidden);

      const button = document.createElement('button');
      button.type = 'submit';
      button.className = 'btn btn-outline-secondary btn-sm';
      button.setAttribute('data-roster-move', '');
      button.setAttribute(
        'aria-label',
        direction === 'up' ? 'Przesuń jednostkę w górę' : 'Przesuń jednostkę w dół',
      );
      button.textContent = direction === 'up' ? '↑' : '↓';
      form.appendChild(button);

      reorder.appendChild(form);
    });
  }

  const item = document.createElement('div');
  item.className =
    'roster-unit-item roster-card text-start position-relative flex-grow-1 border rounded p-3 bg-body';
  item.setAttribute('data-roster-item', '');
  if (itemId) {
    item.setAttribute('data-roster-unit-id', itemId);
  }
  item.setAttribute('data-unit-name', unitName);
  item.setAttribute('data-unit-count', String(count));
  item.setAttribute('data-unit-cost', String(cachedCost));
  item.setAttribute('data-base-cost-per-model', String(baseCostPerModel));
  item.setAttribute('data-unit-quality', String(unitQuality));
  item.setAttribute('data-unit-defense', String(unitDefense));
  item.setAttribute('data-unit-toughness', String(unitToughness));
  item.setAttribute('data-unit-custom-name', customName);
  if (data.unit_flags !== undefined && data.unit_flags !== null) {
    item.setAttribute('data-unit-flags', String(data.unit_flags));
  }
  item.setAttribute('data-default-summary', defaultSummary || '');
  item.setAttribute('data-weapon-options', toJsonString(data.weapon_options, []));
  item.setAttribute('data-passives', toJsonString(data.passive_items, []));
  item.setAttribute('data-actives', toJsonString(data.active_items, []));
  item.setAttribute('data-auras', toJsonString(data.aura_items, []));
  item.setAttribute('data-selected-passives', toJsonString(data.selected_passive_items, []));
  item.setAttribute('data-selected-actives', toJsonString(data.selected_active_items, []));
  item.setAttribute('data-selected-auras', toJsonString(data.selected_aura_items, []));
  item.setAttribute('data-loadout', toJsonString(data.loadout, {}));
  item.setAttribute('data-unit-classification', toJsonString(data.classification, null));
  item.setAttribute('role', 'button');
  item.setAttribute('tabindex', '0');

  const costBadge = document.createElement('span');
  costBadge.className = 'badge text-bg-primary roster-cost-badge';
  costBadge.setAttribute('data-roster-unit-cost', '');
  costBadge.textContent = `${formatPoints(cachedCost)} pkt`;
  item.appendChild(costBadge);

  const title = document.createElement('div');
  title.className = 'fw-semibold';
  title.setAttribute('data-roster-unit-title', '');
  title.textContent = `${count}x ${unitName}`;
  item.appendChild(title);

  const custom = document.createElement('div');
  custom.className = 'text-muted small';
  custom.setAttribute('data-roster-unit-custom', '');
  const trimmedCustom = customName.trim();
  custom.textContent = trimmedCustom;
  if (!trimmedCustom) {
    custom.classList.add('d-none');
  }
  item.appendChild(custom);

  const stats = document.createElement('div');
  stats.className = 'text-muted small';
  stats.textContent = `Jakość ${unitQuality} / Obrona ${unitDefense} / Wytrzymałość ${unitToughness}`;
  item.appendChild(stats);

  const abilities = document.createElement('div');
  abilities.className = 'd-flex flex-wrap gap-1 mt-2';
  abilities.setAttribute('data-roster-unit-abilities', '');
  item.appendChild(abilities);

  const loadoutEl = document.createElement('div');
  loadoutEl.className = 'text-muted small mt-2';
  loadoutEl.setAttribute('data-roster-unit-loadout', '');
  loadoutEl.textContent = `Uzbrojenie: ${loadoutSummary || '-'}`;
  item.appendChild(loadoutEl);

  entry.appendChild(item);

  return outer;
}

function renderPassiveEditor(
  container,
  items,
  stateMap,
  modelCount,
  editable,
  onChange,
  getDelta,
) {
  if (!container) {
    return false;
  }
  container.innerHTML = '';
  const safeItems = Array.isArray(items) ? items : [];
  if (!safeItems.length) {
    return false;
  }
  const totalModels = Math.max(Number(modelCount) || 0, 0);
  const wrapper = document.createElement('div');
  wrapper.className = 'd-flex flex-column gap-2';
  safeItems.forEach((entry) => {
    if (!entry || !entry.slug) {
      return;
    }
    const slug = String(entry.slug);
    const normalizedSlug = slug.trim().toLowerCase();
    const isLockedAbility = Boolean(entry.is_mandatory);
    let currentValue = Number(stateMap.get(slug));
    if (!Number.isFinite(currentValue)) {
      currentValue = Number(entry.default_count ?? (entry.is_default ? 1 : 0));
    }
    if (!Number.isFinite(currentValue) || currentValue <= 0) {
      currentValue = 0;
    } else {
      currentValue = 1;
    }
    if (isLockedAbility) {
      currentValue = 1;
    }
    stateMap.set(slug, currentValue);

    const row = document.createElement('div');
    row.className = 'roster-ability-item';

    const info = document.createElement('div');
    info.className = 'roster-ability-details flex-grow-1';
    const name = document.createElement('span');
    name.className = 'roster-ability-label';
    name.textContent = entry.label || entry.raw || slug;
    if (entry.description) {
      name.title = entry.description;
    }
    info.appendChild(name);
    const cost = document.createElement('span');
    cost.className = 'roster-ability-cost';
    const costValue = Number(entry.cost);
    const multiplier = Math.max(totalModels, 1);
    let currentFlag = currentValue > 0 ? 1 : 0;
    if (isLockedAbility) {
      currentFlag = 1;
    }
    const computeDelta = () => {
      if (typeof getDelta === 'function') {
        try {
          const context = {
            slug,
            entry,
            currentFlag,
            models: totalModels,
          };
          const deltaResult = getDelta(context);
          if (deltaResult && typeof deltaResult === 'object' && Object.prototype.hasOwnProperty.call(deltaResult, 'diff')) {
            const diffValue = Number(deltaResult.diff);
            if (Number.isFinite(diffValue)) {
              return diffValue;
            }
          }
          const numericResult = Number(deltaResult);
          if (Number.isFinite(numericResult)) {
            return numericResult;
          }
        } catch (err) {
          console.warn('Nie udało się obliczyć kosztu zdolności pasywnej', slug, err);
        }
      }
      if (Number.isFinite(costValue)) {
        return costValue * multiplier;
      }
      return Number.NaN;
    };
    let deltaValue = computeDelta();
    const formatDeltaText = () => {
      if (!Number.isFinite(deltaValue) || Math.abs(deltaValue) < 1e-9) {
        return 'Δ 0 pkt';
      }
      const prefix = deltaValue > 0 ? '+' : '-';
      return `Δ ${prefix}${formatPoints(Math.abs(deltaValue))} pkt`;
    };
    cost.textContent = formatDeltaText();
    info.appendChild(cost);
    row.appendChild(info);

    const controls = document.createElement('div');
    controls.className = 'roster-ability-controls text-end';

    if (editable) {
      const wrapperCheck = document.createElement('div');
      wrapperCheck.className = 'form-check form-switch mb-0';
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.className = 'form-check-input';
      input.id = `passive-${slug}-${Math.random().toString(16).slice(2)}`;
      input.checked = currentFlag > 0;
      if (isLockedAbility) {
        input.disabled = true;
      }
      const label = document.createElement('label');
      label.className = 'form-check-label small';
      label.setAttribute('for', input.id);
      const updateLabel = () => {
        if (isLockedAbility) {
          label.textContent = 'Zawsze aktywna';
          return;
        }
        label.textContent = input.checked ? 'Aktywna' : 'Wyłączona';
      };
      updateLabel();
      if (!isLockedAbility) {
        input.addEventListener('change', () => {
          const flag = input.checked ? 1 : 0;
          stateMap.set(slug, flag);
          currentFlag = flag;
          deltaValue = computeDelta();
          cost.textContent = formatDeltaText();
          updateLabel();
          if (typeof onChange === 'function') {
            onChange();
          }
        });
      }
      wrapperCheck.appendChild(input);
      wrapperCheck.appendChild(label);
      controls.appendChild(wrapperCheck);
    } else {
      const status = document.createElement('div');
      status.className = 'text-muted small';
      status.textContent = currentFlag > 0 ? 'Aktywna' : 'Wyłączona';
      controls.appendChild(status);
    }

    row.appendChild(controls);
    wrapper.appendChild(row);
  });

  if (!wrapper.childElementCount) {
    return false;
  }
  container.appendChild(wrapper);
  return true;
}

function normalizeLoadoutKey(rawKey) {
  if (rawKey === undefined || rawKey === null) {
    return '';
  }
  if (typeof rawKey === 'string') {
    const trimmed = rawKey.trim();
    return trimmed ? trimmed : '';
  }
  if (typeof rawKey === 'number') {
    return Number.isFinite(rawKey) ? String(rawKey) : '';
  }
  if (typeof rawKey === 'bigint') {
    return rawKey.toString();
  }
  const numeric = Number(rawKey);
  if (Number.isFinite(numeric)) {
    return String(numeric);
  }
  const text = String(rawKey).trim();
  return text ? text : '';
}

function resolveLoadoutEntryKey(entry, ...idKeys) {
  if (!entry || typeof entry !== 'object') {
    return '';
  }
  const candidates = [];
  const loadoutKey = entry.loadout_key ?? entry.loadoutKey;
  if (loadoutKey !== undefined && loadoutKey !== null) {
    candidates.push(loadoutKey);
  }
  const flatIdKeys = [];
  idKeys.forEach((key) => {
    if (!key) {
      return;
    }
    if (Array.isArray(key)) {
      key.forEach((inner) => {
        if (inner) {
          flatIdKeys.push(inner);
        }
      });
      return;
    }
    flatIdKeys.push(key);
  });
  flatIdKeys.push('id');
  const seen = new Set();
  flatIdKeys.forEach((key) => {
    if (!key || seen.has(key)) {
      return;
    }
    seen.add(key);
    if (Object.prototype.hasOwnProperty.call(entry, key)) {
      candidates.push(entry[key]);
    }
  });
  for (let index = 0; index < candidates.length; index += 1) {
    const normalized = normalizeLoadoutKey(candidates[index]);
    if (normalized) {
      return normalized;
    }
  }
  return '';
}

function createLoadoutState(rawLoadout) {
  const state = {
    weapons: new Map(),
    active: new Map(),
    aura: new Map(),
    passive: new Map(),
    activeLabels: new Map(),
    auraLabels: new Map(),
    mode: 'per_model',
  };
  if (!rawLoadout || typeof rawLoadout !== 'object') {
    return state;
  }
  if (typeof rawLoadout.mode === 'string') {
    state.mode = rawLoadout.mode;
  }
  const sections = [
    ['weapons', 'weapon_id'],
    ['active', 'ability_id'],
    ['aura', 'ability_id'],
  ];
  sections.forEach(([section, idKey]) => {
    const values = rawLoadout[section];
    if (!values) {
      return;
    }
    let entries;
    if (Array.isArray(values)) {
      entries = values;
    } else if (typeof values === 'object') {
      entries = Object.entries(values).map(([id, count]) => ({ id, per_model: count }));
    } else {
      entries = [];
    }
    entries.forEach((entry) => {
      if (!entry) {
        return;
      }
      const key = resolveLoadoutEntryKey(entry, idKey, ['weapon_id', 'ability_id']);
      if (!key) {
        return;
      }
      const rawCount = entry.per_model ?? entry.count ?? 0;
      let parsedCount = Number(rawCount);
      if (!Number.isFinite(parsedCount) || parsedCount < 0) {
        parsedCount = 0;
      }
      state[section].set(key, parsedCount);
    });
  });
  const passiveSource = rawLoadout.passive;
  if (passiveSource && typeof passiveSource === 'object') {
    let entries;
    if (Array.isArray(passiveSource)) {
      entries = passiveSource;
    } else {
      entries = Object.entries(passiveSource).map(([slug, enabled]) => ({ slug, enabled }));
    }
    entries.forEach((entry) => {
      if (!entry) {
        return;
      }
      const slug = entry.slug ?? entry.id;
      if (slug === undefined || slug === null) {
        return;
      }
      const rawValue = entry.enabled ?? entry.count ?? entry.value;
      const numeric = Number(rawValue);
      let flag = 0;
      if (typeof rawValue === 'boolean') {
        flag = rawValue ? 1 : 0;
      } else if (Number.isFinite(numeric)) {
        flag = numeric > 0 ? 1 : 0;
      } else if (rawValue) {
        flag = 1;
      }
      state.passive.set(String(slug), flag);
    });
  }
  const labelSections = [
    ['activeLabels', rawLoadout.active_labels],
    ['auraLabels', rawLoadout.aura_labels],
  ];
  labelSections.forEach(([targetKey, source]) => {
    const target = state[targetKey];
    if (!(target instanceof Map) || !source) {
      return;
    }
    let entries;
    if (Array.isArray(source)) {
      entries = source;
    } else if (typeof source === 'object') {
      entries = Object.entries(source).map(([id, name]) => ({
        id,
        name,
      }));
    } else {
      entries = [];
    }
    entries.forEach((entry) => {
      if (!entry) {
        return;
      }
      const key = resolveLoadoutEntryKey(entry, 'ability_id');
      if (!key) {
        return;
      }
      const rawName = entry.name ?? entry.value ?? entry.label;
      if (rawName === undefined || rawName === null) {
        return;
      }
      const trimmed = String(rawName).trim().slice(0, ABILITY_NAME_MAX_LENGTH);
      if (!trimmed) {
        return;
      }
      target.set(key, trimmed);
    });
  });
  return state;
}

function cloneLoadoutState(state) {
  const cloneSection = (section) => {
    if (section instanceof Map) {
      return new Map(section);
    }
    return new Map();
  };
  if (!state || typeof state !== 'object') {
    return {
      weapons: new Map(),
      active: new Map(),
      aura: new Map(),
      passive: new Map(),
      activeLabels: new Map(),
      auraLabels: new Map(),
      mode: 'per_model',
    };
  }
  return {
    weapons: cloneSection(state.weapons),
    active: cloneSection(state.active),
    aura: cloneSection(state.aura),
    passive: cloneSection(state.passive),
    activeLabels: cloneSection(state.activeLabels),
    auraLabels: cloneSection(state.auraLabels),
    mode: state.mode === 'total' ? 'total' : 'per_model',
  };
}

function serializeLoadoutState(state) {
  const result = {
    weapons: [],
    active: [],
    aura: [],
    passive: [],
    active_labels: [],
    aura_labels: [],
    mode: 'total',
  };
  if (!state) {
    return JSON.stringify(result);
  }
  result.mode = state.mode === 'total' ? 'total' : 'per_model';
  state.weapons.forEach((value, id) => {
    result.weapons.push({ id, count: value });
  });
  state.active.forEach((value, id) => {
    result.active.push({ id, count: value });
  });
  state.aura.forEach((value, id) => {
    result.aura.push({ id, count: value });
  });
  state.passive.forEach((value, slug) => {
    result.passive.push({ slug, enabled: Boolean(value) });
  });
  if (state.activeLabels instanceof Map) {
    state.activeLabels.forEach((value, id) => {
      const text = typeof value === 'string' ? value.trim() : String(value || '').trim();
      if (!text) {
        return;
      }
      result.active_labels.push({ id, name: text.slice(0, ABILITY_NAME_MAX_LENGTH) });
    });
  }
  if (state.auraLabels instanceof Map) {
    state.auraLabels.forEach((value, id) => {
      const text = typeof value === 'string' ? value.trim() : String(value || '').trim();
      if (!text) {
        return;
      }
      result.aura_labels.push({ id, name: text.slice(0, ABILITY_NAME_MAX_LENGTH) });
    });
  }
  return JSON.stringify(result);
}

function ensureStateEntries(map, entries, idKey, defaultKey, options = {}) {
  const safeEntries = Array.isArray(entries) ? entries : [];
  const fallbackIdKeys = Array.isArray(options.fallbackIdKeys) ? options.fallbackIdKeys : [];
  safeEntries.forEach((entry) => {
    if (!entry) {
      return;
    }
    const key = resolveLoadoutEntryKey(entry, idKey, fallbackIdKeys);
    if (!key) {
      return;
    }
    let defaultCount = Number(entry[defaultKey] ?? 0);
    if (!Number.isFinite(defaultCount) || defaultCount < 0) {
      defaultCount = 0;
    }
    if (!map.has(key)) {
      map.set(key, defaultCount);
    }
  });
}

function ensurePassiveStateEntries(map, entries) {
  const safeEntries = Array.isArray(entries) ? entries : [];
  safeEntries.forEach((entry) => {
    if (!entry) {
      return;
    }
    const slug = entry.slug || entry.value || entry.label;
    if (!slug) {
      return;
    }
    let defaultCount = Number(entry.default_count ?? (entry.is_default ? 1 : 0));
    if (!Number.isFinite(defaultCount) || defaultCount <= 0) {
      defaultCount = 0;
    } else {
      defaultCount = 1;
    }
    const key = String(slug);
    if (!map.has(key)) {
      map.set(key, defaultCount);
    }
  });
}

function formatAbilityDisplayLabel(baseLabel, customName) {
  const base = typeof baseLabel === 'string' ? baseLabel.trim() : '';
  const custom = typeof customName === 'string' ? customName.trim() : '';
  if (custom && base) {
    return `${custom} [${base}]`;
  }
  if (custom) {
    return custom;
  }
  return base;
}

function renderAbilityEditor(
  container,
  items,
  stateMap,
  labelMap = null,
  modelCount,
  editable,
  onChange,
) {

  if (!container) {
    return false;
  }
  container.innerHTML = '';
  const safeItems = Array.isArray(items) ? items : [];
  if (!safeItems.length) {
    return false;
  }
  const wrapper = document.createElement('div');
  wrapper.className = 'd-flex flex-column gap-2';
  const safeLabelMap = labelMap instanceof Map ? labelMap : null;
  const maxCount = Math.max(Number(modelCount) || 0, 0);
  safeItems.forEach((item) => {
    if (!item) {
      return;
    }
    const abilityKey = resolveLoadoutEntryKey(item, 'ability_id');
    if (!abilityKey) {
      return;
    }
    let totalCount = Number(stateMap.get(abilityKey));
    if (!Number.isFinite(totalCount) || totalCount < 0) {
      totalCount = Number(item.default_count ?? 0);
      if (!Number.isFinite(totalCount) || totalCount < 0) {
        totalCount = 0;
      }
    }
    if (maxCount > 0 && totalCount > maxCount) {
      totalCount = maxCount;
    }
    stateMap.set(abilityKey, totalCount);

    const row = document.createElement('div');
    row.className = 'roster-ability-item';

    const info = document.createElement('div');
    info.className = 'roster-ability-details flex-grow-1';
    const name = document.createElement('span');
    name.className = 'roster-ability-label';
    const baseLabel = item.label || 'Zdolność';

    let customName = '';
    if (safeLabelMap && safeLabelMap.has(abilityKey)) {
      const override = safeLabelMap.get(abilityKey);
      if (typeof override === 'string') {
        customName = override.trim();
      } else if (override !== undefined && override !== null) {
        customName = String(override).trim();
      }
    }
    if (!customName && typeof item.custom_name === 'string') {
      customName = item.custom_name;
    }
    if (item.description) {
      name.title = item.description;
    }
    name.textContent = formatAbilityDisplayLabel(baseLabel, customName);

    info.appendChild(name);
    const cost = document.createElement('span');
    cost.className = 'roster-ability-cost';
    if (item.cost !== undefined && item.cost !== null) {
      cost.textContent = `+${formatPoints(item.cost)} pkt/model`;
    } else {
      cost.textContent = 'wliczone';
    }
    info.appendChild(cost);

    if (!editable && customName) {
      const customInfo = document.createElement('div');
      customInfo.className = 'text-muted small mt-1';
      customInfo.textContent = `Nazwa własna: ${customName}`;

      info.appendChild(customInfo);
    }
    row.appendChild(info);

    const controls = document.createElement('div');
    controls.className = 'roster-ability-controls text-end';
    if (editable) {
      const input = document.createElement('input');
      input.type = 'number';
      input.className = 'form-control form-control-sm roster-count-input';
      input.min = '0';
      input.value = String(totalCount);
      if (maxCount > 0) {
        input.max = String(maxCount);
      }
      input.addEventListener('change', () => {
        let nextValue = Number(input.value);
        if (!Number.isFinite(nextValue) || nextValue < 0) {
          nextValue = 0;
        }
        if (maxCount > 0 && nextValue > maxCount) {
          nextValue = maxCount;
        }
        input.value = String(nextValue);
        stateMap.set(abilityKey, nextValue);
        const hasCustomInput = typeof customInput !== 'undefined' && customInput;
        if (nextValue <= 0) {
          if (typeof applyCustomName === 'function') {
            applyCustomName('');
          }
          if (hasCustomInput) {
            customInput.value = '';
            customInput.disabled = true;
          }
        } else if (hasCustomInput) {
          customInput.disabled = false;
          if (typeof formatDisplayLabel === 'function' && currentCustomName) {
            formatDisplayLabel(currentCustomName);
          }
        }
        if (typeof onChange === 'function') {
          onChange();
        }
      });
      controls.appendChild(input);
    } else {
      const valueDisplay = document.createElement('div');
      valueDisplay.className = 'text-muted small';
      valueDisplay.textContent = `${formatPoints(totalCount)} szt.`;
      controls.appendChild(valueDisplay);
    }

    row.appendChild(controls);
    wrapper.appendChild(row);
  });
  if (!wrapper.childElementCount) {
    return false;
  }
  container.appendChild(wrapper);
  return true;
}

function toggleSectionVisibility(container, isVisible) {
  if (!container) {
    return;
  }
  const wrapper = container.closest('[data-roster-section]');
  if (wrapper) {
    wrapper.classList.toggle('d-none', !isVisible);
  }
}

function renderWeaponEditor(
  container,
  options,
  stateMap,
  modelCount,
  editable,
  onChange,
  stateMode = 'total',
) {
  if (!container) {
    return false;
  }
  container.innerHTML = '';
  const safeOptions = Array.isArray(options) ? options : [];
  if (!safeOptions.length) {
    return false;
  }
  const normalizedMode = stateMode === 'per_model' ? 'per_model' : 'total';
  const numericModelCount = Math.max(Number(modelCount) || 0, 0);
  const weaponInfoMap = new Map();
  const classInfoMap = new Map();
  const inputRefs = new Map();
  const wrapper = document.createElement('div');
  wrapper.className = 'd-flex flex-column gap-2';
  const parseSafeNumber = (value) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric < 0) {
      return 0;
    }
    return numeric;
  };
  const getStoredCount = (key, fallback = 0) => {
    if (!(stateMap instanceof Map) || !key) {
      return 0;
    }
    const stored = Number(stateMap.get(key));
    if (Number.isFinite(stored) && stored >= 0) {
      return stored;
    }
    const fallbackNumeric = Number(fallback);
    if (Number.isFinite(fallbackNumeric) && fallbackNumeric >= 0) {
      return fallbackNumeric;
    }
    return 0;
  };
  safeOptions.forEach((option) => {
    if (!option || option.id === undefined || option.id === null) {
      return;
    }
    const weaponId = Number(option.id);
    if (!Number.isFinite(weaponId)) {
      return;
    }
    const weaponKey = resolveLoadoutEntryKey(option, 'id', ['weapon_id']);
    if (!weaponKey) {
      return;
    }
    const normalizedRange = normalizeRangeValue(option.range);
    const weaponClass = normalizedRange > 0 ? 'ranged' : 'melee';
    const defaultPerModel = parseSafeNumber(option.default_count ?? (option.is_default ? 1 : 0));
    const isDefaultWeapon = Boolean(option.is_default) || defaultPerModel > 0;
    const isPrimaryWeapon = Boolean(option.is_primary) && defaultPerModel > 0;
    const weaponMeta = {
      option,
      weaponKey,
      weaponClass,
      defaultPerModel,
      isPrimaryWeapon,
      isDefaultWeapon,
      currentValue: 0,
    };
    weaponInfoMap.set(weaponKey, weaponMeta);
    let classInfo = classInfoMap.get(weaponClass);
    if (!classInfo) {
      classInfo = {
        classKey: weaponClass,
        weapons: [],
        defaultWeapon: null,
        capacity: 0,
        total: 0,
      };
      classInfoMap.set(weaponClass, classInfo);
    }
    let totalCount = Number(stateMap.get(weaponKey));
    if (!Number.isFinite(totalCount) || totalCount < 0) {
      totalCount = Number(option.default_count ?? 0);
      if (!Number.isFinite(totalCount) || totalCount < 0) {
        totalCount = 0;
      }
    }
    stateMap.set(weaponKey, totalCount);
    weaponMeta.currentValue = totalCount;
    classInfo.weapons.push(weaponMeta);
    classInfo.total += totalCount;
    const assignDefaultWeapon = () => {
      classInfo.defaultWeapon = weaponMeta;
      let capacity = defaultPerModel;
      if (normalizedMode === 'total') {
        const multiplier = numericModelCount > 0 ? numericModelCount : 1;
        capacity *= multiplier;
      }
      if (!Number.isFinite(capacity) || capacity <= 0) {
        capacity = totalCount;
      }
      classInfo.capacity = capacity;
    };
    if (isPrimaryWeapon) {
      assignDefaultWeapon();
    } else if (!classInfo.defaultWeapon && isDefaultWeapon) {
      assignDefaultWeapon();
    }

    const row = document.createElement('div');
    row.className = 'roster-ability-item';

    const info = document.createElement('div');
    info.className = 'roster-ability-details flex-grow-1';
    const name = document.createElement('span');
    name.className = 'roster-ability-label';
    name.textContent = option.name || 'Broń';
    info.appendChild(name);
    const cost = document.createElement('span');
    cost.className = 'roster-ability-cost';
    if (option.cost !== undefined && option.cost !== null) {
      cost.textContent = `+${formatPoints(option.cost)} pkt/model`;
    } else {
      cost.textContent = 'wliczone';
    }
    info.appendChild(cost);
    const statsLine = document.createElement('div');
    statsLine.className = 'text-muted small mt-1';
    const rangeText = option.range !== undefined && option.range !== null && option.range !== '' ? option.range : '-';
    const attacksText = option.attacks !== undefined && option.attacks !== null && option.attacks !== ''
      ? option.attacks
      : '-';
    const apText = option.ap !== undefined && option.ap !== null && option.ap !== '' ? option.ap : 0;
    const traitsText = option.traits ? String(option.traits) : 'Brak cech';
    statsLine.textContent = `Zasięg: ${rangeText} • Ataki: ${attacksText} • AP: ${apText} • Cechy: ${traitsText}`;
    info.appendChild(statsLine);
    row.appendChild(info);

    const controls = document.createElement('div');
    controls.className = 'roster-ability-controls text-end';
    if (editable) {
      const input = document.createElement('input');
      input.type = 'number';
      input.className = 'form-control form-control-sm roster-count-input';
      input.min = '0';
      input.value = String(totalCount);
      inputRefs.set(weaponKey, input);
      input.addEventListener('change', () => {
        let nextValue = Number(input.value);
        if (!Number.isFinite(nextValue) || nextValue < 0) {
          nextValue = 0;
        }
        input.value = String(nextValue);
        const weaponInfo = weaponInfoMap.get(weaponKey);
        const classInfo = weaponInfo ? classInfoMap.get(weaponInfo.weaponClass) : null;
        const previousValue = getStoredCount(weaponKey);
        let delta = nextValue - previousValue;
        let defaultPrevious = null;
        let defaultNext = null;
        if (
          weaponInfo
          && classInfo
          && classInfo.defaultWeapon
          && classInfo.defaultWeapon.weaponKey !== weaponKey
          && delta !== 0
        ) {
          const defaultWeapon = classInfo.defaultWeapon;
          const defaultKey = defaultWeapon.weaponKey;
          defaultPrevious = getStoredCount(defaultKey);
          const otherTotal = classInfo.weapons.reduce((sum, entry) => {
            if (!entry || entry.weaponKey === weaponKey || entry.weaponKey === defaultKey) {
              return sum;
            }
            return sum + getStoredCount(entry.weaponKey);
          }, 0);
          if (delta > 0) {
            defaultNext = Math.max(defaultPrevious - delta, 0);
          } else {
            const baselineTotal = defaultPrevious + previousValue + otherTotal;
            const effectiveCapacity = Math.max(classInfo.capacity, baselineTotal);
            const desiredDefault = defaultPrevious - delta;
            const maxDefault = Math.max(effectiveCapacity - (otherTotal + nextValue), 0);
            if (desiredDefault > maxDefault) {
              defaultNext = maxDefault;
              const recalculatedOptional = Math.max(
                effectiveCapacity - (otherTotal + defaultNext),
                0,
              );
              if (recalculatedOptional !== nextValue) {
                nextValue = recalculatedOptional;
                delta = nextValue - previousValue;
                input.value = String(nextValue);
              }
            } else {
              defaultNext = desiredDefault;
            }
          }
          if (defaultNext !== null && defaultNext !== defaultPrevious) {
            stateMap.set(defaultKey, defaultNext);
            defaultWeapon.currentValue = defaultNext;
            const defaultInput = inputRefs.get(defaultKey);
            if (defaultInput && defaultInput !== input) {
              defaultInput.value = String(defaultNext);
            }
          }
        }
        stateMap.set(weaponKey, nextValue);
        if (weaponInfo) {
          weaponInfo.currentValue = nextValue;
        }
        if (classInfo) {
          classInfo.total = classInfo.weapons.reduce((sum, entry) => {
            if (!entry) {
              return sum;
            }
            return sum + getStoredCount(entry.weaponKey);
          }, 0);
        }
        if (
          typeof onChange === 'function'
          && (delta !== 0
            || (defaultPrevious !== null && defaultNext !== null && defaultNext !== defaultPrevious))
        ) {
          onChange();
        }
      });
      controls.appendChild(input);
    } else {
      const valueDisplay = document.createElement('div');
      valueDisplay.className = 'text-muted small';
      valueDisplay.textContent = `${formatPoints(totalCount)} szt.`;
      controls.appendChild(valueDisplay);
    }

    row.appendChild(controls);
    wrapper.appendChild(row);
  });
  classInfoMap.forEach((classInfo) => {
    if (!classInfo) {
      return;
    }
    if (!Number.isFinite(classInfo.capacity) || classInfo.capacity <= 0) {
      classInfo.capacity = classInfo.total;
    }
  });
  if (!wrapper.childElementCount) {
    return false;
  }
  container.appendChild(wrapper);
  return true;
}

function computeTotalCost(
  basePerModel,
  modelCount,
  weaponOptions,
  state,
  costMaps,
  passiveItems,
  weaponCostOverrides
) {
  const count = Math.max(Number(modelCount) || 0, 0);
  if (count <= 0) {
    return 0;
  }
  let total = Number(basePerModel) * count;
  if (!Number.isFinite(total)) {
    total = 0;
  }
  const stateMode = state && state.mode === 'total' ? 'total' : 'per_model';
  const toTotal = (value) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) {
      return 0;
    }
    return stateMode === 'total' ? numeric : numeric * count;
  };
  const weaponCostMap = new Map();
  if (weaponCostOverrides instanceof Map) {
    weaponCostOverrides.forEach((value, key) => {
      const weaponId = Number(key);
      const numericValue = Number(value);
      if (Number.isFinite(weaponId) && Number.isFinite(numericValue)) {
        weaponCostMap.set(weaponId, numericValue);
      }
    });
  }
  const safeOptions = Array.isArray(weaponOptions) ? weaponOptions : [];
  safeOptions.forEach((option) => {
    if (!option || option.id === undefined || option.id === null) {
      return;
    }
    const weaponId = Number(option.id);
    const costValue = Number(option.cost);
    if (
      Number.isFinite(weaponId)
      && Number.isFinite(costValue)
      && !weaponCostMap.has(weaponId)
    ) {
      weaponCostMap.set(weaponId, costValue);
    }
  });

  if (state && state.weapons instanceof Map) {
    state.weapons.forEach((value, weaponId) => {
      const totalCount = toTotal(value);
      if (totalCount <= 0) {
        return;
      }
      const costValue = weaponCostMap.get(Number(weaponId));
      if (Number.isFinite(costValue)) {
        total += costValue * totalCount;
      }
    });
  }

  const activeCostMap = costMaps && costMaps.active instanceof Map ? costMaps.active : new Map();
  const passiveCostMap = costMaps && costMaps.passive instanceof Map ? costMaps.passive : new Map();
  [state && state.active, state && state.aura].forEach((section) => {
    if (!(section instanceof Map)) {
      return;
    }
    section.forEach((value, abilityId) => {
      const totalCount = toTotal(value);
      if (totalCount <= 0) {
        return;
      }
      const canonicalKey = normalizeLoadoutKey(abilityId) || String(abilityId);
      let costValue = activeCostMap.get(canonicalKey);
      if (!Number.isFinite(costValue) && canonicalKey !== abilityId) {
        costValue = activeCostMap.get(abilityId);
      }
      if (!Number.isFinite(costValue)) {
        const numericKey = Number(canonicalKey);
        if (Number.isFinite(numericKey)) {
          costValue = activeCostMap.get(String(numericKey));
          if (!Number.isFinite(costValue)) {
            costValue = activeCostMap.get(numericKey);
          }
        }
      }
      if (Number.isFinite(costValue)) {
        total += costValue * totalCount;
      }
    });
  });

  const passiveList = Array.isArray(passiveItems) ? passiveItems : [];
  const passiveState = state && state.passive instanceof Map ? state.passive : new Map();
  if (passiveList.length) {
    passiveList.forEach((item) => {
      if (!item || !item.slug) {
        return;
      }
      const key = String(item.slug);
      const defaultValue = Number(item.default_count ?? (item.is_default ? 1 : 0));
      const baseFlag = Number.isFinite(defaultValue) && defaultValue > 0 ? 1 : 0;
      const storedValue = Number(passiveState.get(key));
      const selectedFlag = Number.isFinite(storedValue) && storedValue > 0 ? 1 : 0;
      const diff = selectedFlag - baseFlag;
      if (diff === 0) {
        return;
      }
      let costValue = passiveCostMap.get(key);
      if (!Number.isFinite(costValue)) {
        costValue = Number(item.cost);
      }
      if (!Number.isFinite(costValue) || costValue === 0) {
        return;
      }
      total += costValue * diff * count;
    });
  }

  return total;
}

function initRosterAdders(root) {
  if (!root) {
    return;
  }
  const registeredForms = new WeakSet();

  function registerForm(form) {
    if (!form || registeredForms.has(form)) {
      return;
    }
    registeredForms.add(form);
    let isSubmitting = false;

    const handleSubmit = async (event) => {
      event.preventDefault();
      if (isSubmitting) {
        return;
      }
      isSubmitting = true;
      const cleanup = () => {
        isSubmitting = false;
      };
      const fallback = () => {
        form.removeEventListener('submit', handleSubmit);
        cleanup();
        form.submit();
      };

      const action = form.getAttribute('action');
      if (!action) {
        fallback();
        return;
      }

      const payload = new FormData(form);

      try {
        const response = await fetch(action, {
          method: 'POST',
          body: payload,
          headers: { Accept: 'application/json' },
          credentials: 'same-origin',
        });
        const contentType = (response.headers.get('content-type') || '').toLowerCase();
        if (!response.ok || !contentType.includes('application/json')) {
          fallback();
          return;
        }
        let data;
        try {
          data = await response.json();
        } catch (err) {
          fallback();
          return;
        }
        if (!data || typeof data !== 'object' || !data.roster_item || !data.unit) {
          fallback();
          return;
        }
        cleanup();
        root.dispatchEvent(
          new CustomEvent('roster:add-unit-success', { detail: { payload: data, form } }),
        );
      } catch (error) {
        console.error('Nie udało się dodać oddziału', error);
        fallback();
      } finally {
        if (isSubmitting) {
          cleanup();
        }
      }
    };

    form.addEventListener('submit', handleSubmit);
  }

  root.querySelectorAll('[data-roster-add-trigger]').forEach((trigger) => {
    const form = trigger.closest('form');
    if (!form) {
      return;
    }
    registerForm(form);
    const submitForm = () => {
      if (typeof form.requestSubmit === 'function') {
        form.requestSubmit();
      } else {
        form.submit();
      }
    };
    trigger.addEventListener('click', (event) => {
      event.preventDefault();
      submitForm();
    });
    trigger.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        submitForm();
      }
    });
  });
}

function renderWarningsList(container, warnings) {
  if (!container) {
    return;
  }
  container.innerHTML = '';
  const list = Array.isArray(warnings) ? warnings : [];
  container.dataset.warnings = JSON.stringify(list);
  if (!list.length) {
    return;
  }
  const alertBox = document.createElement('div');
  alertBox.className = 'alert alert-warning mb-0';
  const strong = document.createElement('strong');
  strong.textContent = 'Ostrzeżenia:';
  alertBox.appendChild(strong);
  const listEl = document.createElement('ul');
  listEl.className = 'mb-0';
  list.forEach((warning) => {
    const item = document.createElement('li');
    item.textContent = String(warning || '');
    listEl.appendChild(item);
  });
  alertBox.appendChild(listEl);
  container.appendChild(alertBox);
}

function initRosterEditor() {
  const root = document.querySelector('[data-roster-root]');
  if (!root) {
    return;
  }
  initRosterAdders(root);
  const rosterId = root.dataset.rosterId || '';
  const editor = root.querySelector('[data-roster-editor]');
  const emptyState = root.querySelector('[data-roster-editor-empty]');
  const nameEl = root.querySelector('[data-roster-editor-name]');
  const statsEl = root.querySelector('[data-roster-editor-stats]');
  const passiveContainer = root.querySelector('[data-roster-editor-passives]');
  const activeContainer = root.querySelector('[data-roster-editor-actives]');
  const auraContainer = root.querySelector('[data-roster-editor-auras]');
  const loadoutContainer = root.querySelector('[data-roster-editor-loadout]');
  const form = root.querySelector('[data-roster-editor-form]');
  const duplicateForm = root.querySelector('[data-roster-editor-duplicate]');
  const deleteForm = root.querySelector('[data-roster-editor-delete]');
  const countInput = root.querySelector('[data-roster-editor-count]');
  const customNameInput = root.querySelector('[data-roster-editor-custom-name]');
  const customLabel = root.querySelector('[data-roster-editor-custom-label]');
  const roleEl = root.querySelector('[data-roster-editor-role]');
  const loadoutInput = root.querySelector('[data-roster-editor-loadout-input]');
  const costValueEl = root.querySelector('[data-roster-editor-cost]');
  const costBadgeEl = root.querySelector('[data-roster-editor-cost-badge]');
  const saveStateEl = root.querySelector('[data-roster-editor-save-state]');
  const totalContainer = root.querySelector('[data-roster-total-container]');
  const totalValueEl = root.querySelector('[data-roster-total]');
  const warningsContainer = document.querySelector('[data-roster-warnings]');
  const isEditable = Boolean(form && countInput && loadoutInput);
  const listWrapper = root.querySelector('[data-roster-items-container]') || null;
  let rosterListEl = root.querySelector('[data-roster-list]');
  const items = [];
  const itemRegistry = new WeakSet();
  if (warningsContainer) {
    try {
      const initialWarnings = JSON.parse(warningsContainer.dataset.warnings || '[]');
      renderWarningsList(warningsContainer, Array.isArray(initialWarnings) ? initialWarnings : []);
    } catch (err) {
      renderWarningsList(warningsContainer, []);
    }
  }

  function ensureRosterList() {
    if (rosterListEl && rosterListEl.isConnected) {
      return rosterListEl;
    }
    rosterListEl = root.querySelector('[data-roster-list]');
    if (rosterListEl) {
      return rosterListEl;
    }
    if (!listWrapper) {
      return null;
    }
    const listElement = document.createElement('div');
    listElement.className = 'list-group roster-unit-list';
    listElement.setAttribute('data-roster-list', '');
    listWrapper.appendChild(listElement);
    rosterListEl = listElement;
    return rosterListEl;
  }

  function removeEmptyPlaceholder() {
    if (!listWrapper) {
      return;
    }
    const placeholder = listWrapper.querySelector('[data-roster-empty]');
    if (placeholder) {
      placeholder.remove();
    }
  }

  function updateMoveButtonStates(listElement) {
    if (!isEditable || !listElement) {
      return;
    }
    const entries = Array.from(listElement.querySelectorAll('.roster-unit-entry'));
    entries.forEach((entry, index) => {
      entry.querySelectorAll('[data-roster-move-form]').forEach((form) => {
        const directionInput = form.querySelector('input[name="direction"]');
        const button = form.querySelector('[data-roster-move]');
        if (!button) {
          return;
        }
        const direction = directionInput ? String(directionInput.value || '') : '';
        if (direction === 'up') {
          button.disabled = index === 0;
        } else if (direction === 'down') {
          button.disabled = index === entries.length - 1;
        }
      });
    });
  }

  function registerRosterItem(item) {
    if (!item || itemRegistry.has(item)) {
      return;
    }
    itemRegistry.add(item);
    items.push(item);
    item.addEventListener('click', () => {
      selectItem(item);
    });
    item.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        selectItem(item);
      }
    });
    const entry = item.closest('.roster-unit-entry');
    if (entry) {
      entry.querySelectorAll('[data-roster-move]').forEach((button) => {
        button.addEventListener('click', (event) => {
          event.stopPropagation();
        });
      });
      entry.querySelectorAll('[data-roster-move-form]').forEach((form) => {
        form.addEventListener('click', (event) => {
          event.stopPropagation();
        });
      });
    }
    const listElement = item.closest('[data-roster-list]') || rosterListEl;
    if (listElement) {
      rosterListEl = listElement;
      updateMoveButtonStates(listElement);
    }
  }

  root.addEventListener('roster:add-unit-success', (event) => {
    if (!event || !event.detail) {
      return;
    }
    const { payload } = event.detail;
    if (!payload || typeof payload !== 'object') {
      return;
    }
    const itemData = payload.roster_item || payload.item;
    if (!itemData || typeof itemData !== 'object') {
      return;
    }
    const listElement = ensureRosterList();
    if (!listElement) {
      return;
    }
    removeEmptyPlaceholder();
    const listItemElement = createRosterItemElement(itemData, {
      rosterId,
      isEditable,
    });
    if (!listItemElement) {
      return;
    }
    listElement.appendChild(listItemElement);
    const rosterItemElement = listItemElement.querySelector('[data-roster-item]');
    if (rosterItemElement) {
      registerRosterItem(rosterItemElement);
    }
    applyServerUpdate(payload);
    if (rosterItemElement) {
      selectItem(rosterItemElement);
      if (typeof listItemElement.scrollIntoView === 'function') {
        listItemElement.scrollIntoView({ block: 'nearest' });
      }
    }
    updateMoveButtonStates(listElement);
  });

  let activeItem = null;
  let loadoutState = createLoadoutState({});
  let currentCount = 1;
  let currentWeapons = [];
  let currentActives = [];
  let currentAuras = [];
  let currentPassives = [];
  let currentBaseFlags = {};
  let currentQuality = 4;
  let currentWeaponCostMap = new Map();
  let abilityCostMap = { active: new Map(), passive: new Map() };
  let baseCostPerModel = 0;
  let currentClassification = null;
  let currentCustomName = '';
  let customEditInput = null;
  let autoSaveEnabled = false;
  let ignoreNextSave = false;
  let saveTimer = null;
  let isSaving = false;
  let pendingSave = false;
  const SAVE_MESSAGES = {
    idle: '',
    dirty: 'Niezapisane zmiany',
    saving: 'Zapisywanie...',
    saved: 'Zapisano',
    error: 'Błąd zapisu',
  };
  let currentSaveStatus = 'idle';
  const customPlaceholder = customLabel ? customLabel.dataset.placeholder || '' : '';
  const rosterDatasetCache = new WeakMap();
  const UNIT_DATASET_KEYS = [
    'weapon_options',
    'passive_items',
    'active_items',
    'aura_items',
    'default_summary',
  ];
  const UNIT_DATASET_ATTRIBUTE_MAP = new Map([
    ['data-weapon-options', 'weapon_options'],
    ['data-passives', 'passive_items'],
    ['data-actives', 'active_items'],
    ['data-auras', 'aura_items'],
    ['data-default-summary', 'default_summary'],
  ]);
  const rosterUnitDatasetRepo = new Map();
  const rosterUnitDatasetCache = new Map();

  (function initializeUnitDatasetRepo() {
    const raw = root.dataset ? root.dataset.rosterUnitDatasets || '' : '';
    if (raw) {
      try {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === 'object') {
          Object.entries(parsed).forEach(([unitId, value]) => {
            if (!unitId || !value || typeof value !== 'object') {
              return;
            }
            rosterUnitDatasetRepo.set(String(unitId), value);
          });
        }
      } catch (err) {
        console.warn('Nie udało się odczytać danych jednostek', err);
      }
    }
    if (root.dataset && Object.prototype.hasOwnProperty.call(root.dataset, 'rosterUnitDatasets')) {
      delete root.dataset.rosterUnitDatasets;
    }
  })();

  function setSaveStatus(status) {
    currentSaveStatus = status;
    if (!saveStateEl) {
      return;
    }
    const message = SAVE_MESSAGES[status] ?? '';
    saveStateEl.textContent = message;
    saveStateEl.classList.remove('text-success', 'text-danger');
    if (status === 'saved') {
      saveStateEl.classList.add('text-success');
    } else if (status === 'error') {
      saveStateEl.classList.add('text-danger');
    }
  }

  function cancelPendingSave() {
    if (saveTimer) {
      window.clearTimeout(saveTimer);
      saveTimer = null;
    }
    pendingSave = false;
  }

  function parseList(value) {
    if (!value) {
      return [];
    }
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      console.warn('Nie udało się odczytać danych oddziału', err);
      return [];
    }
  }

  function parseLoadout(value) {
    if (!value) {
      return {};
    }
    try {
      const parsed = JSON.parse(value);
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch (err) {
      console.warn('Nie udało się odczytać konfiguracji oddziału', err);
      return {};
    }
  }

  function parseJsonValue(value) {
    if (!value) {
      return null;
    }
    try {
      return JSON.parse(value);
    } catch (err) {
      return null;
    }
  }

  function resolveUnitCacheId(source) {
    if (source === null || source === undefined) {
      return '';
    }
    if (typeof source === 'string' || typeof source === 'number') {
      const text = String(source).trim();
      return text ? text : '';
    }
    if (source instanceof Element) {
      return source.getAttribute('data-unit-cache-id') || '';
    }
    return '';
  }

  function getUnitDatasetEntry(source) {
    const cacheId = resolveUnitCacheId(source);
    if (!cacheId) {
      return null;
    }
    let entry = rosterUnitDatasetCache.get(cacheId);
    if (!entry) {
      entry = {
        data: rosterUnitDatasetRepo.get(cacheId) || null,
        values: new Map(),
      };
      rosterUnitDatasetCache.set(cacheId, entry);
    }
    return entry;
  }

  function getUnitDatasetValue(source, datasetKey, fallback = null) {
    const cacheId = resolveUnitCacheId(source);
    if (!cacheId || !datasetKey) {
      return fallback;
    }
    const entry = getUnitDatasetEntry(cacheId);
    if (!entry || !entry.data) {
      return fallback;
    }
    if (entry.values.has(datasetKey)) {
      const cached = entry.values.get(datasetKey);
      return cached === undefined ? fallback : cached;
    }
    const value = entry.data[datasetKey];
    entry.values.set(datasetKey, value);
    return value === undefined ? fallback : value;
  }

  function getUnitDatasetList(source, datasetKey) {
    const value = getUnitDatasetValue(source, datasetKey, []);
    return Array.isArray(value) ? value : [];
  }

  function updateUnitDataset(source, updates) {
    const cacheId = resolveUnitCacheId(source);
    if (!cacheId || !updates || typeof updates !== 'object') {
      return;
    }
    const normalizedUpdates = {};
    UNIT_DATASET_KEYS.forEach((key) => {
      if (Object.prototype.hasOwnProperty.call(updates, key)) {
        const value = updates[key];
        if (value !== undefined) {
          normalizedUpdates[key] = value;
        }
      }
    });
    const updateKeys = Object.keys(normalizedUpdates);
    if (!updateKeys.length) {
      return;
    }
    const previous = rosterUnitDatasetRepo.get(cacheId);
    const next = previous && typeof previous === 'object' ? { ...previous } : {};
    updateKeys.forEach((key) => {
      next[key] = normalizedUpdates[key];
    });
    rosterUnitDatasetRepo.set(cacheId, next);
    rosterUnitDatasetCache.delete(cacheId);
  }

  function getCacheEntry(item, attribute, rawValue) {
    if (!item || !attribute) {
      return null;
    }
    let cache = rosterDatasetCache.get(item);
    if (!cache) {
      cache = new Map();
      rosterDatasetCache.set(item, cache);
    }
    let entry = cache.get(attribute);
    if (!entry || entry.raw !== rawValue) {
      entry = { raw: rawValue, list: undefined, objects: new Map() };
      cache.set(attribute, entry);
    }
    return entry;
  }

  function invalidateCachedAttribute(item, attribute) {
    if (!item || !attribute) {
      return;
    }
    const cache = rosterDatasetCache.get(item);
    if (!cache) {
      return;
    }
    cache.delete(attribute);
    if (cache.size === 0) {
      rosterDatasetCache.delete(item);
    }
  }

  function getParsedList(item, attribute) {
    if (!item || !attribute) {
      return [];
    }
    const datasetKey = UNIT_DATASET_ATTRIBUTE_MAP.get(attribute);
    if (datasetKey) {
      const cacheId = resolveUnitCacheId(item);
      if (cacheId) {
        return getUnitDatasetList(cacheId, datasetKey);
      }
    }
    const rawValue = item.getAttribute(attribute) || '';
    const entry = getCacheEntry(item, attribute, rawValue);
    if (!entry) {
      return parseList(rawValue);
    }
    if (entry.list !== undefined) {
      return entry.list;
    }
    const parsed = parseList(rawValue);
    entry.list = parsed;
    return parsed;
  }

  function getParsedObject(item, attribute, parser = parseJsonValue) {
    if (!item || !attribute) {
      return parser ? parser('') : null;
    }
    const rawValue = item.getAttribute(attribute) || '';
    const entry = getCacheEntry(item, attribute, rawValue);
    if (!entry) {
      return parser ? parser(rawValue) : null;
    }
    const parserKey = parser || '__default__';
    if (entry.objects.has(parserKey)) {
      return entry.objects.get(parserKey);
    }
    const parsed = parser ? parser(rawValue) : null;
    entry.objects.set(parserKey, parsed);
    return parsed;
  }

  function updateCustomLabelDisplay(value) {
    if (!customLabel) {
      return;
    }
    const text = value ? String(value) : customPlaceholder;
    customLabel.textContent = text;
    if (customPlaceholder) {
      const showPlaceholder = !value;
      customLabel.classList.toggle('text-opacity-50', showPlaceholder);
      customLabel.classList.toggle('fst-italic', showPlaceholder);
    }
  }

  function updateListCustomName(item, value) {
    if (!item) {
      return;
    }
    const customEl = item.querySelector('[data-roster-unit-custom]');
    if (!customEl) {
      return;
    }
    if (value) {
      customEl.textContent = value;
      customEl.classList.remove('d-none');
    } else {
      customEl.textContent = '';
      customEl.classList.add('d-none');
    }
  }

  function setCustomName(rawValue, options = {}) {
    const trimmed = (rawValue || '').trim();
    const previous = currentCustomName;
    currentCustomName = trimmed;
    if (customNameInput) {
      customNameInput.value = trimmed;
    }
    if (!customEditInput) {
      updateCustomLabelDisplay(trimmed);
    }
    if (options.updateActiveItem !== false && activeItem) {
      activeItem.setAttribute('data-unit-custom-name', trimmed);
    }
    if (options.updateList !== false && activeItem) {
      updateListCustomName(activeItem, trimmed);
    }
    if (autoSaveEnabled && options.triggerSave !== false && trimmed !== previous) {
      setSaveStatus('dirty');
      scheduleSave();
    }
  }

  function startCustomInlineEdit() {
    if (!isEditable || !customLabel || customEditInput) {
      return;
    }
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'form-control form-control-sm';
    input.maxLength = 120;
    input.value = currentCustomName;
    customEditInput = input;
    customLabel.textContent = '';
    customLabel.appendChild(input);
    window.setTimeout(() => {
      input.focus();
      input.select();
    }, 0);
    const finish = (commit) => {
      if (!customEditInput) {
        return;
      }
      const nextValue = commit ? customEditInput.value : currentCustomName;
      customEditInput.remove();
      customEditInput = null;
      setCustomName(nextValue, {
        triggerSave: commit,
        updateActiveItem: true,
        updateList: true,
      });
    };
    input.addEventListener('blur', () => finish(true));
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        finish(true);
      } else if (event.key === 'Escape') {
        event.preventDefault();
        finish(false);
      }
    });
  }

  function renderClassificationDisplay() {
    if (!roleEl) {
      return;
    }
    roleEl.textContent = '';
    roleEl.classList.add('d-none');
  }

  function updateItemClassification(item, classification) {
    if (!item) {
      return;
    }
    try {
      item.setAttribute('data-unit-classification', JSON.stringify(classification ?? null));
    } catch (err) {
      item.setAttribute('data-unit-classification', 'null');
    }
    invalidateCachedAttribute(item, 'data-unit-classification');
  }

  function syncDefaultEquipment(previousCount, nextCount) {
    if (!loadoutState) {
      return;
    }
    const prev = Math.max(Number(previousCount) || 0, 0);
    const next = Math.max(Number(nextCount) || 0, 0);
    if (prev === next) {
      return;
    }
    const adjust = (map, items, idKey, fallbackIdKeys = []) => {
      if (!(map instanceof Map)) {
        return;
      }
      const safeItems = Array.isArray(items) ? items : [];
      safeItems.forEach((item) => {
        if (!item) {
          return;
        }
        const key = resolveLoadoutEntryKey(item, idKey, fallbackIdKeys);
        if (!key) {
          return;
        }
        const defaultValue = Number(item.default_count ?? 0);
        if (!Number.isFinite(defaultValue) || defaultValue <= 0) {
          return;
        }
        const prevTotal = prev * defaultValue;
        const stored = Number(map.get(key));
        const diff = Number.isFinite(stored) ? stored - prevTotal : 0;
        const nextTotal = Math.max(next * defaultValue + diff, 0);
        map.set(key, nextTotal);
      });
    };
    adjust(loadoutState.weapons, currentWeapons, 'id', ['weapon_id']);
    adjust(loadoutState.active, currentActives, 'ability_id', ['id']);
    adjust(loadoutState.aura, currentAuras, 'ability_id', ['id']);
  }

  function buildAbilityCostMap(activeItems, auraItems, passiveItems) {
    const activeMap = new Map();
    const passiveMap = new Map();
    [...(Array.isArray(activeItems) ? activeItems : []), ...(Array.isArray(auraItems) ? auraItems : [])].forEach((item) => {
      if (!item) {
        return;
      }
      const abilityKey = resolveLoadoutEntryKey(item, 'ability_id');
      const costValue = Number(item.cost);
      if (abilityKey && Number.isFinite(costValue)) {
        activeMap.set(abilityKey, costValue);
      }
    });
    (Array.isArray(passiveItems) ? passiveItems : []).forEach((item) => {
      if (!item || !item.slug) {
        return;
      }
      const costValue = Number(item.cost);
      if (Number.isFinite(costValue)) {
        passiveMap.set(String(item.slug), costValue);
      }
    });
    return { active: activeMap, passive: passiveMap };
  }

  function updateTotalSummary(total) {
    if (!totalValueEl) {
      return;
    }
    totalValueEl.textContent = formatPoints(total);
  }

  function scheduleSave() {
    if (!isEditable || !form || !autoSaveEnabled) {
      return;
    }
    if (saveTimer) {
      window.clearTimeout(saveTimer);
    }
    saveTimer = window.setTimeout(() => {
      saveTimer = null;
      if (isSaving) {
        pendingSave = true;
        return;
      }
      setSaveStatus('saving');
      isSaving = true;
      submitChanges()
        .catch((error) => {
          console.error('Nie udało się zapisać zmian oddziału', error);
          setSaveStatus('error');
        })
        .finally(() => {
          isSaving = false;
          if (pendingSave) {
            pendingSave = false;
            scheduleSave();
          }
        });
    }, 400);
  }

  async function submitChanges() {
    if (!form || !activeItem) {
      throw new Error('Brak aktywnego oddziału');
    }
    const action = form.getAttribute('action');
    if (!action) {
      throw new Error('Brak adresu zapisu');
    }
    const payload = new FormData(form);
    payload.set('count', String(currentCount));
    if (customNameInput) {
      payload.set('custom_name', customNameInput.value.trim());
    }
    if (loadoutInput) {
      payload.set('loadout_json', loadoutInput.value || '{}');
    }
    const response = await fetch(action, {
      method: 'POST',
      body: payload,
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();
    applyServerUpdate(data || {});
    setSaveStatus('saved');
  }

  function setItemListAttribute(element, attribute, list) {
    if (!element) {
      return;
    }
    const safeList = Array.isArray(list) ? list : [];
    try {
      element.setAttribute(attribute, JSON.stringify(safeList));
    } catch (error) {
      element.setAttribute(attribute, '[]');
    }
    invalidateCachedAttribute(element, attribute);
  }

  function abilityBadgeLabel(entry) {
    if (!entry) {
      return '';
    }
    const base = entry.label ?? entry.raw ?? entry.slug ?? '';
    const custom = entry.custom_name ?? entry.customName ?? '';
    const trimmedCustom = typeof custom === 'string' ? custom.trim() : '';
    if (trimmedCustom) {
      return base ? `${trimmedCustom} [${base}]` : trimmedCustom;
    }
    return base;
  }

  function updateItemAbilityBadges(item, selections) {
    if (!item) {
      return;
    }
    const container = item.querySelector('[data-roster-unit-abilities]');
    if (!container) {
      return;
    }
    container.innerHTML = '';
    const config = [
      { key: 'passives', className: 'badge text-bg-secondary', showCount: false },
      { key: 'actives', className: 'badge text-bg-info text-dark', showCount: true },
      { key: 'auras', className: 'badge text-bg-warning text-dark', showCount: true },
    ];
    let hasContent = false;
    config.forEach(({ key, className, showCount }) => {
      const list = selections && Array.isArray(selections[key]) ? selections[key] : [];
      list.forEach((entry) => {
        if (!entry) {
          return;
        }
        const label = abilityBadgeLabel(entry);
        if (!label) {
          return;
        }
        const badge = document.createElement('span');
        badge.className = className;
        if (entry.description) {
          badge.title = entry.description;
        }
        let text = String(label);
        if (showCount) {
          const numeric = Number(entry.count);
          if (Number.isFinite(numeric) && numeric > 1) {
            text += ` ×${numeric}`;
          }
        }
        badge.textContent = text;
        container.appendChild(badge);
        hasContent = true;
      });
    });
    if (!hasContent) {
      const empty = document.createElement('span');
      empty.className = 'text-muted small';
      empty.textContent = 'Brak dodatkowych zdolności';
      container.appendChild(empty);
    }
  }

  function syncEditorFromItem(item, options = {}) {
    const {
      preserveAutoSave = false,
      updateFormActions = false,
      ensureEditorVisible = false,
    } = options;
    if (!item || !editor || !emptyState) {
      return;
    }
    if (!preserveAutoSave) {
      autoSaveEnabled = false;
      setSaveStatus('idle');
    } else if (!isEditable) {
      autoSaveEnabled = false;
    }
    if (customEditInput) {
      customEditInput.remove();
      customEditInput = null;
    }

    currentPassives = getUnitDatasetList(item, 'passive_items');
    currentActives = getUnitDatasetList(item, 'active_items');
    currentAuras = getUnitDatasetList(item, 'aura_items');
    currentWeapons = getUnitDatasetList(item, 'weapon_options');
    currentBaseFlags = parseFlagString(item.getAttribute('data-unit-flags'));

    const unitName = item.getAttribute('data-unit-name') || 'Jednostka';
    const quality = item.getAttribute('data-unit-quality') || '-';
    const qualityNumeric = Number(quality);
    currentQuality = Number.isFinite(qualityNumeric) ? qualityNumeric : 4;
    const defense = item.getAttribute('data-unit-defense') || '-';
    const toughness = item.getAttribute('data-unit-toughness') || '-';
    const countValue = Number(item.getAttribute('data-unit-count') || '1');
    const baseCostValue = Number(item.getAttribute('data-base-cost-per-model') || '0');
    const rosterUnitId = item.getAttribute('data-roster-unit-id');
    const loadoutData = getParsedObject(item, 'data-loadout', parseLoadout);
    const customName = item.getAttribute('data-unit-custom-name') || '';
    const classificationData = getParsedObject(item, 'data-unit-classification', parseJsonValue);

    currentClassification =
      classificationData && typeof classificationData === 'object' ? classificationData : null;

    if (nameEl) {
      nameEl.textContent = unitName;
    }
    if (statsEl) {
      statsEl.textContent = `Jakość ${quality} / Obrona ${defense} / Wytrzymałość ${toughness}`;
    }

    setCustomName(customName, {
      triggerSave: false,
      updateActiveItem: false,
      updateList: false,
    });
    renderClassificationDisplay();

    currentCount = Number.isFinite(countValue) && countValue >= 1 ? countValue : 1;
    if (countInput) {
      countInput.value = String(currentCount);
    }

    loadoutState = createLoadoutState(loadoutData);
    ensureStateEntries(loadoutState.weapons, currentWeapons, 'id', 'default_count', {
      fallbackIdKeys: ['weapon_id'],
    });
    ensureStateEntries(loadoutState.active, currentActives, 'ability_id', 'default_count', {
      fallbackIdKeys: ['id'],
    });
    ensureStateEntries(loadoutState.aura, currentAuras, 'ability_id', 'default_count', {
      fallbackIdKeys: ['id'],
    });
    ensurePassiveStateEntries(loadoutState.passive, currentPassives);
    if (loadoutState.mode !== 'total') {
      const convertToTotal = (map) => {
        if (!(map instanceof Map)) {
          return;
        }
        map.forEach((value, key) => {
          const numeric = Number(value);
          if (!Number.isFinite(numeric) || numeric <= 0) {
            map.set(key, 0);
            return;
          }
          map.set(key, numeric * currentCount);
        });
      };
      convertToTotal(loadoutState.weapons);
      convertToTotal(loadoutState.active);
      convertToTotal(loadoutState.aura);
      loadoutState.mode = 'total';
    }

    abilityCostMap = buildAbilityCostMap(currentActives, currentAuras, currentPassives);
    baseCostPerModel = Number.isFinite(baseCostValue) && baseCostValue >= 0 ? baseCostValue : 0;

    ignoreNextSave = true;
    handleStateChange();

    if (updateFormActions && rosterUnitId) {
      if (form) {
        form.setAttribute('action', `/rosters/${rosterId}/units/${rosterUnitId}/update`);
      }
      if (duplicateForm) {
        duplicateForm.setAttribute(
          'action',
          `/rosters/${rosterId}/units/${rosterUnitId}/duplicate`,
        );
      }
      if (deleteForm) {
        deleteForm.setAttribute('action', `/rosters/${rosterId}/units/${rosterUnitId}/delete`);
      }
    }

    if (ensureEditorVisible) {
      editor.classList.remove('d-none');
      emptyState.classList.add('d-none');
    }

    autoSaveEnabled = isEditable;
    setSaveStatus(currentSaveStatus);
  }

  function applyServerUpdate(payload) {
    if (!payload || typeof payload !== 'object') {
      return;
    }
    const unitData = payload.unit || {};
    const unitId = unitData && unitData.id !== undefined ? String(unitData.id) : '';
    const isActiveMatch = Boolean(
      activeItem && unitId && activeItem.getAttribute('data-roster-unit-id') === unitId,
    );
    const targetItem = isActiveMatch
      ? activeItem
      : unitId
        ? root.querySelector(`[data-roster-item][data-roster-unit-id="${unitId}"]`)
        : null;
    if (unitData && targetItem) {
      const unitCacheId = resolveUnitCacheId(targetItem);
      if (unitCacheId) {
        const datasetUpdates = {};
        UNIT_DATASET_KEYS.forEach((key) => {
          if (Object.prototype.hasOwnProperty.call(unitData, key)) {
            datasetUpdates[key] = unitData[key];
          }
        });
        if (Object.keys(datasetUpdates).length) {
          updateUnitDataset(unitCacheId, datasetUpdates);
        }
      }
      if (typeof unitData.count === 'number' && Number.isFinite(unitData.count)) {
        targetItem.setAttribute('data-unit-count', String(unitData.count));
      }
      if (typeof unitData.cached_cost === 'number' && Number.isFinite(unitData.cached_cost)) {
        targetItem.setAttribute('data-unit-cost', String(unitData.cached_cost));
      }
      if (
        typeof unitData.base_cost_per_model === 'number'
        && Number.isFinite(unitData.base_cost_per_model)
      ) {
        targetItem.setAttribute('data-base-cost-per-model', String(unitData.base_cost_per_model));
      }
      if (unitData.custom_name !== undefined) {
        const serverName = typeof unitData.custom_name === 'string' ? unitData.custom_name : '';
        targetItem.setAttribute('data-unit-custom-name', serverName);
        updateListCustomName(targetItem, serverName.trim());
      }
      if (typeof unitData.loadout_json === 'string') {
        targetItem.setAttribute('data-loadout', unitData.loadout_json);
        invalidateCachedAttribute(targetItem, 'data-loadout');
      }
      if (Object.prototype.hasOwnProperty.call(unitData, 'selected_passive_items')) {
        setItemListAttribute(
          targetItem,
          'data-selected-passives',
          unitData.selected_passive_items,
        );
      }
      if (Object.prototype.hasOwnProperty.call(unitData, 'selected_active_items')) {
        setItemListAttribute(
          targetItem,
          'data-selected-actives',
          unitData.selected_active_items,
        );
      }
      if (Object.prototype.hasOwnProperty.call(unitData, 'selected_aura_items')) {
        setItemListAttribute(targetItem, 'data-selected-auras', unitData.selected_aura_items);
      }
      const unitName = targetItem.getAttribute('data-unit-name') || 'Jednostka';
      if (typeof unitData.count === 'number' && Number.isFinite(unitData.count)) {
        const titleEl = targetItem.querySelector('[data-roster-unit-title]');
        if (titleEl) {
          titleEl.textContent = `${unitData.count}x ${unitName}`;
        }
      }
      const costBadge = targetItem.querySelector('[data-roster-unit-cost]');
      if (costBadge && typeof unitData.cached_cost === 'number') {
        costBadge.textContent = `${formatPoints(unitData.cached_cost)} pkt`;
      }
      const loadoutEl = targetItem.querySelector('[data-roster-unit-loadout]');
      if (loadoutEl) {
        const defaultSummary =
          getUnitDatasetValue(unitCacheId || targetItem, 'default_summary', unitData.default_summary || '-') || '-';
        const summary = unitData.loadout_summary || defaultSummary;
        loadoutEl.textContent = `Uzbrojenie: ${summary || '-'}`;
      }
      if (Object.prototype.hasOwnProperty.call(unitData, 'classification')) {
        updateItemClassification(targetItem, unitData.classification || null);
      }
      updateItemAbilityBadges(targetItem, {
        passives: unitData.selected_passive_items || [],
        actives: unitData.selected_active_items || [],
        auras: unitData.selected_aura_items || [],
      });
      if (isActiveMatch) {
        syncEditorFromItem(targetItem, { preserveAutoSave: true });
      }
    }
    let totalCostValue = null;
    if (typeof payload.total_cost === 'number') {
      totalCostValue = payload.total_cost;
    } else if (payload.roster && typeof payload.roster.total_cost === 'number') {
      totalCostValue = payload.roster.total_cost;
    }
    if (Number.isFinite(totalCostValue)) {
      updateTotalSummary(totalCostValue);
    }
    if (Array.isArray(payload.warnings)) {
      renderWarningsList(warningsContainer, payload.warnings);
    }
  }

  function updateCostDisplays() {
    const total = computeTotalCost(
      baseCostPerModel,
      currentCount,
      currentWeapons,
      loadoutState,
      abilityCostMap,
      currentPassives,
      currentWeaponCostMap,
    );
    const formatted = formatPoints(total);
    if (costValueEl) {
      costValueEl.textContent = formatted;
    }
    if (costBadgeEl) {
      costBadgeEl.classList.toggle('d-none', false);
    }
    if (activeItem) {
      activeItem.setAttribute('data-unit-cost', String(total));
      const listBadge = activeItem.querySelector('[data-roster-unit-cost]');
      if (listBadge) {
        listBadge.textContent = `${formatted} pkt`;
      }
    }
    return total;
  }

  function applyClassificationToState(state, classification) {
    if (!state || !(state.passive instanceof Map)) {
      return;
    }
    let targetIdentifier = null;
    let targetKey = null;
    if (classification && typeof classification === 'object' && classification.slug) {
      const slugText = String(classification.slug);
      const normalized = abilityIdentifier(slugText);
      if (normalized && CLASSIFICATION_SLUGS.has(normalized)) {
        targetIdentifier = normalized;
        const stripped = slugText.trim();
        if (stripped) {
          targetKey = stripped;
        }
      }
    }
    const passiveMap = state.passive;
    Array.from(passiveMap.keys()).forEach((key) => {
      const ident = passiveIdentifier(key);
      if (!CLASSIFICATION_SLUGS.has(ident)) {
        return;
      }
      if (targetIdentifier && ident === targetIdentifier && targetKey === null) {
        targetKey = String(key);
        passiveMap.set(key, 1);
        return;
      }
      passiveMap.delete(key);
    });
    if (targetIdentifier) {
      const finalKey = targetKey !== null && targetKey !== undefined ? String(targetKey) : targetIdentifier;
      passiveMap.set(finalKey, 1);
    }
  }

  function handleStateChange() {
    let precomputedWeaponMap = null;
    if (loadoutState) {
      loadoutState.mode = 'total';
      const estimation = estimateClassificationForState();
      if (estimation) {
        currentClassification = estimation.classification || null;
        if (estimation.weaponMap instanceof Map) {
          precomputedWeaponMap = estimation.weaponMap;
        }
      }
      applyClassificationToState(loadoutState, currentClassification);
    }

    renderEditors(precomputedWeaponMap);
    if (loadoutInput && loadoutState) {
      loadoutInput.value = serializeLoadoutState(loadoutState);
    }
    updateCostDisplays();
    if (activeItem && loadoutInput) {
      activeItem.setAttribute('data-loadout', loadoutInput.value || '{}');
      invalidateCachedAttribute(activeItem, 'data-loadout');
    }
    if (activeItem) {
      updateItemClassification(activeItem, currentClassification);
      activeItem.setAttribute('data-unit-count', String(currentCount));
    }
    if (ignoreNextSave) {
      ignoreNextSave = false;
      return;
    }
    if (autoSaveEnabled) {
      setSaveStatus('dirty');
      scheduleSave();
    }
  }

function availableClassificationSlugs(flags) {
  const result = new Set();
  Object.keys(flags || {}).forEach((key) => {
    const ident = passiveIdentifier(key);
    if (CLASSIFICATION_SLUGS.has(ident)) {
      result.add(ident);
    }
  });
  return result;
}

function createClassificationPayload(warriorTotal, shooterTotal, availableSlugs) {
  const warrior = Math.max(Number(warriorTotal) || 0, 0);
  const shooter = Math.max(Number(shooterTotal) || 0, 0);
  if (warrior <= 0 && shooter <= 0) {
    return null;
  }
  const pool = new Set();
  if (availableSlugs instanceof Set) {
    availableSlugs.forEach((slug) => {
      if (CLASSIFICATION_SLUGS.has(slug)) {
        pool.add(slug);
      }
    });
  } else if (Array.isArray(availableSlugs)) {
    availableSlugs.forEach((slug) => {
      if (CLASSIFICATION_SLUGS.has(slug)) {
        pool.add(slug);
      }
    });
  }
  let preferred = null;
  if (warrior > shooter) {
    preferred = 'wojownik';
  } else if (shooter > warrior) {
    preferred = 'strzelec';
  } else if (pool.has('wojownik') || pool.size === 0) {
    preferred = 'wojownik';
  } else if (pool.has('strzelec')) {
    preferred = 'strzelec';
  }
  const fallbackSlug = 'wojownik';
  let slug = null;
  if (pool.size) {
    if (preferred && pool.has(preferred)) {
      slug = preferred;
    } else if (pool.size === 1) {
      slug = pool.values().next().value;
    } else if (preferred && !pool.has(preferred)) {
      for (const candidate of pool) {
        if (candidate !== preferred) {
          slug = candidate;
          break;
        }
      }
    } else if (!preferred) {
      if (pool.has('wojownik')) {
        slug = 'wojownik';
      } else if (pool.has('strzelec')) {
        slug = 'strzelec';
      } else {
        slug = pool.values().next().value || null;
      }
    }
  } else {
    slug = preferred || fallbackSlug;
  }
  if (!slug) {
    return null;
  }
  const roundedWarrior = Math.round(warrior * 100) / 100;
  const roundedShooter = Math.round(shooter * 100) / 100;
  const warriorPoints = Math.round(warrior);
  const shooterPoints = Math.round(shooter);
  const display = `Wojownik ${warriorPoints} pkt / Strzelec ${shooterPoints} pkt`;
  return {
    slug,
    label: slug === 'wojownik' ? 'Wojownik' : 'Strzelec',
    warrior_cost: roundedWarrior,
    shooter_cost: roundedShooter,
    display,
  };
}

function estimateClassificationForState() {
  if (!loadoutState) {
    return { classification: null, weaponMap: null };
  }
  const available = availableClassificationSlugs(currentBaseFlags);
  if (currentClassification && typeof currentClassification === 'object' && currentClassification.slug) {
    const ident = abilityIdentifier(currentClassification.slug);
    if (CLASSIFICATION_SLUGS.has(ident)) {
      available.add(ident);
    }
  }
  if (!available.size) {
    return { classification: null, weaponMap: null };
  }
  const evaluateRole = (slug) => {
    const classification = { slug };
    const clone = cloneLoadoutState(loadoutState);
    if (clone) {
      clone.mode = 'total';
    }
    applyClassificationToState(clone, classification);
    const passiveMap = clone && clone.passive instanceof Map ? clone.passive : new Map();
    const weaponMap = buildWeaponCostMap(
      currentWeapons,
      currentQuality,
      currentBaseFlags,
      currentPassives,
      passiveMap,
      classification,
    );
    const total = computeTotalCost(
      baseCostPerModel,
      currentCount,
      currentWeapons,
      clone,
      abilityCostMap,
      currentPassives,
      weaponMap,
    );
    return { total, weaponMap };
  };
  const warrior = available.has('wojownik') ? evaluateRole('wojownik') : null;
  const shooter = available.has('strzelec') ? evaluateRole('strzelec') : null;
  const classification = createClassificationPayload(
    warrior ? warrior.total : 0,
    shooter ? shooter.total : 0,
    available,
  );
  let weaponMap = null;
  if (classification) {
    if (classification.slug === 'wojownik' && warrior) {
      weaponMap = warrior.weaponMap;
    } else if (classification.slug === 'strzelec' && shooter) {
      weaponMap = shooter.weaponMap;
    }
  } else if (warrior && !shooter) {
    weaponMap = warrior.weaponMap;
  } else if (shooter && !warrior) {
    weaponMap = shooter.weaponMap;
  }
  return { classification, weaponMap };
}

function renderEditors(precomputedWeaponMap = null) {
    const passiveState = loadoutState && loadoutState.passive instanceof Map ? loadoutState.passive : new Map();
    if (precomputedWeaponMap instanceof Map) {
      currentWeaponCostMap = precomputedWeaponMap;
    } else {
      currentWeaponCostMap = buildWeaponCostMap(
        currentWeapons,
        currentQuality,
        currentBaseFlags,
        currentPassives,
        passiveState,
        currentClassification,
      );
    }
    const computePassiveDeltaForSlug = (slug) => {
      if (!slug) {
        return Number.NaN;
      }
      const normalizedSlug = String(slug);
      const evaluateTotal = (flag) => {
        const nextState = cloneLoadoutState(loadoutState);
        const passiveClone = nextState.passive instanceof Map ? nextState.passive : new Map();
        passiveClone.set(normalizedSlug, flag > 0 ? 1 : 0);
        nextState.passive = passiveClone;
        const nextWeaponMap = buildWeaponCostMap(
          currentWeapons,
          currentQuality,
          currentBaseFlags,
          currentPassives,
          passiveClone,
          currentClassification,
        );
        return computeTotalCost(
          baseCostPerModel,
          currentCount,
          currentWeapons,
          nextState,
          abilityCostMap,
          currentPassives,
          nextWeaponMap,
        );
      };
      const enabledTotal = evaluateTotal(1);
      const disabledTotal = evaluateTotal(0);
      if (!Number.isFinite(enabledTotal) || !Number.isFinite(disabledTotal)) {
        return Number.NaN;
      }
      return enabledTotal - disabledTotal;
    };
    const decoratedWeapons = Array.isArray(currentWeapons)
      ? currentWeapons.map((option) => {
          if (!option || option.id === undefined || option.id === null) {
            return option;
          }
          const weaponId = Number(option.id);
          const override = currentWeaponCostMap.get(weaponId);
          if (!Number.isFinite(override)) {
            return option;
          }
          return { ...option, cost: override };
        })
      : [];
    const hasPassives = renderPassiveEditor(
      passiveContainer,
      currentPassives,
      passiveState,
      currentCount,
      isEditable,
      handleStateChange,
      (context) => {
        if (!context || !context.slug) {
          return Number.NaN;
        }
        return computePassiveDeltaForSlug(context.slug);
      },
    );
    toggleSectionVisibility(passiveContainer, hasPassives);
    const hasActives = renderAbilityEditor(
      activeContainer,
      currentActives,
      loadoutState.active,
      loadoutState.activeLabels,
      currentCount,
      isEditable,
      handleStateChange,
    );
    toggleSectionVisibility(activeContainer, hasActives);
    const hasAuras = renderAbilityEditor(
      auraContainer,
      currentAuras,
      loadoutState.aura,
      loadoutState.auraLabels,
      currentCount,
      isEditable,
      handleStateChange,
    );
    toggleSectionVisibility(auraContainer, hasAuras);
    const hasWeapons = renderWeaponEditor(
      loadoutContainer,
      decoratedWeapons,
      loadoutState.weapons,
      currentCount,
      isEditable,
      handleStateChange,
      loadoutState ? loadoutState.mode : 'total',
    );
    toggleSectionVisibility(loadoutContainer, hasWeapons);
  }

  function selectItem(item, options = {}) {
    const { preserveAutoSave = false } = options;
    if (!preserveAutoSave && activeItem === item) {
      return;
    }
    cancelPendingSave();
    if (activeItem) {
      activeItem.classList.remove('active');
    }
    activeItem = item;
    if (activeItem) {
      activeItem.classList.add('active');
    }
    if (!editor || !emptyState) {
      return;
    }
    if (!item) {
      editor.classList.add('d-none');
      emptyState.classList.remove('d-none');
      if (customNameInput) {
        customNameInput.value = '';
      }
      currentCustomName = '';
      if (customEditInput) {
        customEditInput.remove();
        customEditInput = null;
      }
      updateCustomLabelDisplay('');
      currentClassification = null;
      renderClassificationDisplay();
      autoSaveEnabled = false;
      setSaveStatus('idle');
      return;
    }

    syncEditorFromItem(item, {
      preserveAutoSave,
      updateFormActions: true,
      ensureEditorVisible: true,
    });
  }

  const initialItems = Array.from(root.querySelectorAll('[data-roster-item]'));
  initialItems.forEach((item) => {
    registerRosterItem(item);
  });
  if (!rosterListEl && initialItems.length) {
    const inferredList = initialItems[0].closest('[data-roster-list]');
    if (inferredList) {
      rosterListEl = inferredList;
    }
  }
  if (rosterListEl) {
    updateMoveButtonStates(rosterListEl);
  }

  if (countInput) {
    countInput.addEventListener('change', () => {
      let nextValue = Number(countInput.value);
      if (!Number.isFinite(nextValue) || nextValue < 1) {
        nextValue = 1;
        countInput.value = '1';
      }
      syncDefaultEquipment(currentCount, nextValue);
      currentCount = nextValue;
      handleStateChange();
    });
  }

  if (customLabel) {
    if (isEditable) {
      customLabel.classList.add('cursor-pointer');
      customLabel.addEventListener('click', (event) => {
        event.preventDefault();
        startCustomInlineEdit();
      });
      customLabel.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          startCustomInlineEdit();
        }
      });
    } else {
      customLabel.classList.remove('cursor-pointer');
      customLabel.setAttribute('tabindex', '-1');
      customLabel.setAttribute('role', 'text');
    }
    updateCustomLabelDisplay('');
  }

  const selectedId = root.dataset.selectedId || '';
  let initialItem = null;
  if (selectedId) {
    initialItem = items.find((element) => element.getAttribute('data-roster-unit-id') === selectedId);
  }
  if (initialItem) {
    selectItem(initialItem);
    if (typeof initialItem.scrollIntoView === 'function') {
      initialItem.scrollIntoView({ block: 'nearest' });
    }
  } else if (items.length) {
    selectItem(items[0]);
  } else if (editor && emptyState) {
    editor.classList.add('d-none');
    emptyState.classList.remove('d-none');
  }
}

function initSpellAbilityForms() {
  document.querySelectorAll('[data-spell-ability-form]').forEach((form) => {
    const abilitySelect = form.querySelector('[data-ability-select]');
    const valueContainer = form.querySelector('[data-ability-value-container]');
    const valueLabelEl = form.querySelector('[data-ability-value-label]');
    const valueSelect = form.querySelector('[data-ability-value-select]');
    const valueInput = form.querySelector('[data-ability-value-input]');
    const valueDescription = form.querySelector('[data-ability-value-description]');
    const passiveListId = form.dataset.passiveAbilityListId || '';

    function resetValueDescription() {
      if (valueDescription) {
        valueDescription.textContent = '';
        valueDescription.classList.add('d-none');
      }
    }

    function setValueInputList(kind) {
      if (!valueInput) {
        return;
      }
      if (kind === 'passive' && passiveListId) {
        valueInput.setAttribute('list', passiveListId);
      } else {
        valueInput.removeAttribute('list');
      }
    }

    function updateValueDescriptionFromSelect() {
      if (!valueDescription || !valueSelect) {
        return;
      }
      const option = valueSelect.selectedOptions && valueSelect.selectedOptions.length > 0 ? valueSelect.selectedOptions[0] : null;
      const description = option && option.dataset ? option.dataset.description || '' : '';
      if (description) {
        valueDescription.textContent = description;
        valueDescription.classList.remove('d-none');
      } else {
        resetValueDescription();
      }
    }

    function hideValueInputs() {
      if (valueContainer) {
        valueContainer.classList.add('d-none');
      }
      if (valueSelect) {
        valueSelect.classList.add('d-none');
        valueSelect.innerHTML = '';
        valueSelect.disabled = true;
      }
      if (valueInput) {
        valueInput.classList.add('d-none');
        valueInput.value = '';
        valueInput.disabled = true;
        valueInput.type = 'text';
        valueInput.removeAttribute('list');
      }
      resetValueDescription();
    }

    function showValueSelect(labelText, choices) {
      if (!valueContainer || !valueSelect) {
        return;
      }
      valueContainer.classList.remove('d-none');
      valueSelect.classList.remove('d-none');
      valueSelect.disabled = false;
      valueSelect.innerHTML = '';
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = labelText ? `Wybierz (${labelText})` : 'Wybierz wartość';
      valueSelect.appendChild(placeholder);
      (choices || []).forEach((choice) => {
        if (choice && typeof choice === 'object') {
          const option = document.createElement('option');
          option.value = choice.value ?? '';
          option.textContent = choice.label ?? choice.value ?? '';
          if (choice.description) {
            option.dataset.description = choice.description;
            option.title = choice.description;
          }
          valueSelect.appendChild(option);
        } else {
          const option = document.createElement('option');
          option.value = choice ?? '';
          option.textContent = choice ?? '';
          valueSelect.appendChild(option);
        }
      });
      if (valueInput) {
        valueInput.classList.add('d-none');
        valueInput.disabled = true;
        setValueInputList('');
      }
      resetValueDescription();
      valueSelect.value = '';
      updateValueDescriptionFromSelect();
    }

    function showValueInput(labelText, valueType, valueKind) {
      if (!valueContainer || !valueInput) {
        return;
      }
      valueContainer.classList.remove('d-none');
      valueInput.classList.remove('d-none');
      valueInput.disabled = false;
      valueInput.placeholder = labelText ? `Wartość (${labelText})` : 'Wartość';
      valueInput.type = valueType === 'number' ? 'number' : 'text';
      setValueInputList(valueKind || '');
      if (valueSelect) {
        valueSelect.classList.add('d-none');
        valueSelect.innerHTML = '';
        valueSelect.disabled = true;
      }
      resetValueDescription();
    }

    const htmlDecoder = document.createElement('textarea');

    function parseChoiceDataset(option) {
      if (!option) {
        return [];
      }
      const rawAttribute = option.getAttribute('data-value-choices') || '';
      const rawDataset = option.dataset.valueChoices || '';
      const raw = rawAttribute || rawDataset;
      if (!raw) {
        return [];
      }
      let decoded = raw;
      if (raw.includes('&')) {
        htmlDecoder.innerHTML = raw;
        decoded = htmlDecoder.value || raw;
      }
      try {
        const parsed = JSON.parse(decoded);
        return Array.isArray(parsed) ? parsed : [];
      } catch (err) {
        if (rawAttribute && rawAttribute !== decoded) {
          try {
            const parsed = JSON.parse(rawAttribute);
            return Array.isArray(parsed) ? parsed : [];
          } catch (innerErr) {
            return [];
          }
        }
        return [];
      }
    }

    function handleAbilityChange() {
      if (!abilitySelect) {
        return;
      }
      resetValueDescription();
      const option = abilitySelect.selectedOptions[0];
      if (!option) {
        hideValueInputs();
        return;
      }
      const requiresValue = option.dataset.requiresValue === 'true';
      if (!requiresValue) {
        hideValueInputs();
        return;
      }
      const labelText = option.dataset.valueLabel || '';
      if (valueLabelEl) {
        valueLabelEl.textContent = labelText ? `Wartość (${labelText})` : 'Wartość';
      }
      const valueKind = option.dataset.valueKind || '';
      const choices = parseChoiceDataset(option);
      if (Array.isArray(choices) && choices.length > 0) {
        showValueSelect(labelText, choices);
      } else {
        const valueType = option.dataset.valueType || 'text';
        showValueInput(labelText, valueType, valueKind);
      }
    }

    if (abilitySelect) {
      abilitySelect.addEventListener('change', handleAbilityChange);
      handleAbilityChange();
    }
    if (valueSelect) {
      valueSelect.addEventListener('change', updateValueDescriptionFromSelect);
    }
  });
}

function initArmoryWeaponTree() {
  const root = document.getElementById('armory-weapons-tree');
  if (!root) {
    return;
  }
  const treeBody = root.querySelector('[data-tree-body]');
  const emptyState = root.querySelector('[data-empty-state]');
  const filterEmptyState = root.querySelector('[data-filter-empty-state]');
  const filterInput = document.getElementById('weapons-filter');
  const sortButtons = Array.from(root.querySelectorAll('[data-sort-key]'));
  const canEdit = root.dataset.canEdit === 'true';
  const highlightWeaponId = root.dataset.highlightWeapon ? String(root.dataset.highlightWeapon) : '';

  let highlightRow = null;
  let highlightScrollPending = Boolean(highlightWeaponId);

  let rawData;
  try {
    rawData = root.dataset.weapons ? JSON.parse(root.dataset.weapons) : [];
  } catch (err) {
    rawData = [];
  }
  const nodeState = new Map();
  const sortState = { key: null, direction: 'none', type: 'text' };
  let filterQuery = '';

  const normalizeText = typeof normalizeName === 'function'
    ? (value) => normalizeName(value || '')
    : (value) => (value === undefined || value === null ? '' : String(value).toLowerCase());

  const nodeLookup = new Map();

  const hydrate = (node, level = 0, orderIndex = 0, parentId = null) => {
    const abilityItems = Array.isArray(node.abilities) ? node.abilities : [];
    const abilityLabels = abilityItems.map((ability) => ability.label || ability.raw || ability.slug || '');
    const abilityDescriptions = abilityItems.map((ability) => ability.description || ability.raw || '');
    const hydrated = {
      ...node,
      abilities: abilityItems,
      level: Number.isFinite(node.level) ? Number(node.level) : level,
      default_order: Number.isFinite(node.default_order) ? Number(node.default_order) : orderIndex,
      nameSort:
        typeof node.name_sort === 'string' && node.name_sort
          ? node.name_sort
          : normalizeText(node.name || ''),
      abilitiesSort:
        typeof node.abilities_sort === 'string' && node.abilities_sort
          ? node.abilities_sort
          : normalizeText(abilityLabels.join(' ')),
      range_value: Number.isFinite(Number(node.range_value))
        ? Number(node.range_value)
        : normalizeRangeValue(node.range),
      attacks_value: Number.isFinite(Number(node.attacks_value))
        ? Number(node.attacks_value)
        : Number(node.attacks ?? 0),
      ap: Number.isFinite(Number(node.ap)) ? Number(node.ap) : Number(node.ap ?? 0),
      cost: Number.isFinite(Number(node.cost)) ? Number(node.cost) : 0,
      cost_display:
        typeof node.cost_display === 'string' && node.cost_display
          ? node.cost_display
          : (Number.isFinite(Number(node.cost)) ? Number(node.cost).toFixed(2) : '0.00'),
      overrides: { ...(node.overrides || {}) },
      parent_id:
        node.parent_id !== undefined && node.parent_id !== null
          ? node.parent_id
          : parentId !== undefined && parentId !== null
            ? parentId
            : null,
      has_parent:
        node.has_parent !== undefined
          ? Boolean(node.has_parent)
          : node.parent_id !== undefined && node.parent_id !== null,
      parent_name: node.parent_name || '',
    };
    if (hydrated.attacks === undefined || hydrated.attacks === null) {
      hydrated.attacks = Math.round(hydrated.attacks_value);
    }
    hydrated.searchText = normalizeText(
      [
        hydrated.name || '',
        hydrated.range || '',
        String(hydrated.attacks ?? ''),
        String(hydrated.ap ?? ''),
        hydrated.parent_name || '',
        abilityLabels.join(' '),
        abilityDescriptions.join(' '),
      ]
        .filter((part) => part && part.length)
        .join(' '),
    );
    nodeLookup.set(String(hydrated.id), hydrated);

    const childLevel = hydrated.level + 1;
    hydrated.children = Array.isArray(node.children)
      ? node.children.map((child, idx) =>
          hydrate(
            child,
            Number.isFinite(child.level) ? Number(child.level) : childLevel,
            Number.isFinite(child.default_order) ? Number(child.default_order) : idx,
            hydrated.id,
          ),
        )
      : [];
    if (!nodeState.has(hydrated.id) && hydrated.children.length) {
      nodeState.set(hydrated.id, { expanded: false });
    }
    return hydrated;
  };

  const treeData = Array.isArray(rawData)
    ? rawData.map((node, index) =>
        hydrate(
          node,
          Number.isFinite(node.level) ? Number(node.level) : 0,
          Number.isFinite(node.default_order) ? Number(node.default_order) : index,
          node.parent_id !== undefined && node.parent_id !== null ? node.parent_id : null,
        ),
      )
    : [];

  if (highlightWeaponId && nodeLookup.has(highlightWeaponId)) {
    const visited = new Set();
    let current = nodeLookup.get(highlightWeaponId);
    while (current && current.parent_id !== null && !visited.has(current.id)) {
      visited.add(current.id);
      const parentId = current.parent_id;
      const state = nodeState.get(parentId) || {};
      if (state.expanded === false) {
        nodeState.set(parentId, { ...state, expanded: true });
      }
      current = nodeLookup.get(String(parentId));
    }
  }

  const restoreDefaultOrder = (nodes) => {
    nodes.sort((a, b) => (a.default_order ?? 0) - (b.default_order ?? 0));
    nodes.forEach((node) => {
      if (Array.isArray(node.children) && node.children.length) {
        restoreDefaultOrder(node.children);
      }
    });
  };

  const updateSortIndicators = () => {
    const indicatorSymbols = { asc: '▲', desc: '▼' };
    sortButtons.forEach((button) => {
      const indicator = button.querySelector('.armory-tree-sort-indicator');
      const key = button.dataset.sortKey;
      const isActive = sortState.key === key && sortState.direction !== 'none';
      button.dataset.sortDirection = isActive ? sortState.direction : 'none';
      if (indicator) {
        indicator.textContent = isActive ? indicatorSymbols[sortState.direction] || '' : '';
      }
    });
  };

  const sortAccessors = {
    name: (node) => node.nameSort || '',
    range: (node) => (Number.isFinite(node.range_value) ? node.range_value : 0),
    attacks: (node) => (Number.isFinite(node.attacks_value) ? node.attacks_value : 0),
    ap: (node) => (Number.isFinite(node.ap) ? node.ap : 0),
    abilities: (node) => node.abilitiesSort || '',
    cost: (node) => (Number.isFinite(node.cost) ? node.cost : 0),
  };

  const sortBranch = (nodes, comparator) => {
    nodes.sort(comparator);
    nodes.forEach((node) => {
      if (Array.isArray(node.children) && node.children.length) {
        sortBranch(node.children, comparator);
      }
    });
  };

  const applySort = () => {
    if (!treeData.length) {
      return;
    }
    if (sortState.direction === 'none' || !sortState.key) {
      restoreDefaultOrder(treeData);
      return;
    }
    restoreDefaultOrder(treeData);
    const accessor = sortAccessors[sortState.key];
    if (typeof accessor !== 'function') {
      return;
    }
    const comparator = (a, b) => {
      const rawA = accessor(a);
      const rawB = accessor(b);
      let result = 0;
      if (sortState.type === 'number') {
        const valueA = Number.isFinite(rawA) ? rawA : Number.NEGATIVE_INFINITY;
        const valueB = Number.isFinite(rawB) ? rawB : Number.NEGATIVE_INFINITY;
        result = valueA - valueB;
      } else {
        const textA = String(rawA || '');
        const textB = String(rawB || '');
        result = textA.localeCompare(textB, undefined, { sensitivity: 'base' });
      }
      if (result === 0) {
        result = (a.default_order ?? 0) - (b.default_order ?? 0);
      }
      return sortState.direction === 'asc' ? result : -result;
    };
    sortBranch(treeData, comparator);
  };

  const computeVisibility = (nodes) => {
    let visibleCount = 0;
    nodes.forEach((node) => {
      const childVisible = computeVisibility(Array.isArray(node.children) ? node.children : []);
      const matches = !filterQuery || node.searchText.includes(filterQuery);
      const isVisible = matches || childVisible > 0;
      node._matches = matches;
      node._visible = isVisible;
      node._visibleChildren = childVisible;
      if (isVisible) {
        visibleCount += 1;
      }
    });
    return visibleCount;
  };

  const createInheritanceLabel = (isOverridden, indentRem = 0) => {
    const label = document.createElement('div');
    label.className = 'text-muted small';
    label.textContent = isOverridden ? 'Nadpisano' : 'Dziedziczone';
    if (indentRem > 0) {
      label.style.paddingLeft = `${indentRem}rem`;
    }
    return label;
  };

  const renderNode = (node, rows) => {
    if (!node._visible) {
      return;
    }
    const isExpanded = filterQuery ? true : (nodeState.get(node.id)?.expanded !== false);
    const row = document.createElement('div');
    row.className = 'armory-tree-row row g-3 align-items-start px-3 py-3 border-bottom';
    row.dataset.nodeId = String(node.id);

    if (highlightWeaponId && String(node.id) === highlightWeaponId) {
      row.classList.add('armory-tree-highlight');
      highlightRow = row;
    }

    const nameCol = document.createElement('div');
    nameCol.className = 'col-12 col-lg-3 d-flex flex-column gap-1';
    const nameWrapper = document.createElement('div');
    nameWrapper.className = 'd-flex align-items-center gap-2';
    const nameIndent = Math.max(0, node.level) * 1.5;
    nameWrapper.style.paddingLeft = `${nameIndent}rem`;

    const toggleContainer = document.createElement('div');
    toggleContainer.className = 'flex-shrink-0';
    const toggleWidthRem = 1.5;
    toggleContainer.style.width = `${toggleWidthRem}rem`;
    if (Array.isArray(node.children) && node.children.length) {
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'btn btn-link btn-sm p-0 armory-tree-toggle';
      toggle.innerHTML = `<span aria-hidden="true">${isExpanded ? '▾' : '▸'}</span>`;
      toggle.setAttribute('aria-label', isExpanded ? 'Zwiń potomne' : 'Rozwiń potomne');
      toggle.disabled = Boolean(filterQuery);
      toggle.addEventListener('click', (event) => {
        event.preventDefault();
        const current = nodeState.get(node.id) || { expanded: true };
        nodeState.set(node.id, { expanded: !current.expanded });
        applyFilterAndRender();
      });
      toggleContainer.appendChild(toggle);
    } else {
      const spacer = document.createElement('span');
      spacer.style.display = 'inline-block';
      spacer.style.width = '0.75rem';
      spacer.style.height = '1rem';
      toggleContainer.appendChild(spacer);
    }
    nameWrapper.appendChild(toggleContainer);

    const nameText = document.createElement('span');
    nameText.textContent = node.name || 'Bez nazwy';
    nameWrapper.appendChild(nameText);
    nameCol.appendChild(nameWrapper);
    if (node.has_parent) {
      const nameLabelIndent = nameIndent + toggleWidthRem;
      nameCol.appendChild(createInheritanceLabel(Boolean(node.overrides?.name), nameLabelIndent));
    }

    const rangeCol = document.createElement('div');
    rangeCol.className = 'col-6 col-sm-4 col-lg-1 d-flex flex-column gap-1';
    const rangeValue = node.range && String(node.range).trim() ? node.range : '-';
    const rangeText = document.createElement('span');
    if (!node.range || !String(node.range).trim()) {
      rangeText.className = 'text-muted';
    }
    rangeText.textContent = rangeValue;
    rangeCol.appendChild(rangeText);
    if (node.has_parent) {
      rangeCol.appendChild(createInheritanceLabel(Boolean(node.overrides?.range)));
    }

    const attacksCol = document.createElement('div');
    attacksCol.className = 'col-6 col-sm-4 col-lg-1 d-flex flex-column gap-1';
    const attacksText = document.createElement('span');
    attacksText.textContent = String(node.attacks ?? Math.round(node.attacks_value ?? 0));
    attacksCol.appendChild(attacksText);
    if (node.has_parent) {
      attacksCol.appendChild(createInheritanceLabel(Boolean(node.overrides?.attacks)));
    }

    const apCol = document.createElement('div');
    apCol.className = 'col-6 col-sm-4 col-lg-1 d-flex flex-column gap-1';
    const apText = document.createElement('span');
    apText.textContent = String(Number.isFinite(node.ap) ? node.ap : 0);
    apCol.appendChild(apText);
    if (node.has_parent) {
      apCol.appendChild(createInheritanceLabel(Boolean(node.overrides?.ap)));
    }

    const abilitiesCol = document.createElement('div');
    abilitiesCol.className = 'col-12 col-lg-3 d-flex flex-column gap-1 mt-2 mt-lg-0 justify-content-lg-center';
    if (Array.isArray(node.abilities) && node.abilities.length) {
      const abilityWrapper = document.createElement('div');
      abilityWrapper.className = 'd-flex flex-wrap gap-1';
      node.abilities.forEach((ability) => {
        const badge = document.createElement('span');
        badge.className = 'badge text-bg-secondary';
        badge.textContent = ability.label || ability.raw || ability.slug || '-';
        const title = ability.description || ability.raw || '';
        if (title) {
          badge.title = title;
        }
        abilityWrapper.appendChild(badge);
      });
      abilitiesCol.appendChild(abilityWrapper);
    } else {
      const empty = document.createElement('span');
      empty.className = 'text-muted';
      empty.textContent = '-';
      abilitiesCol.appendChild(empty);
    }
    if (node.has_parent) {
      abilitiesCol.appendChild(createInheritanceLabel(Boolean(node.overrides?.tags)));
    }

    const costCol = document.createElement('div');
    costCol.className = 'col-6 col-sm-4 col-lg-1 d-flex flex-column gap-1 mt-2 mt-lg-0 justify-content-lg-center';
    const costText = document.createElement('span');
    costText.textContent = node.cost_display || Number(node.cost || 0).toFixed(2);
    costCol.appendChild(costText);

    const actionsCol = document.createElement('div');
    actionsCol.className = 'col-12 col-lg-2 d-flex justify-content-lg-end align-items-lg-center mt-2 mt-lg-0';
    if (canEdit) {
      const group = document.createElement('div');
      group.className = 'btn-group btn-group-sm';
      const editLink = document.createElement('a');
      editLink.className = 'btn btn-outline-secondary';
      editLink.href = node.edit_url;
      editLink.textContent = 'Edytuj';
      group.appendChild(editLink);

      const deleteForm = document.createElement('form');
      deleteForm.method = 'post';
      deleteForm.action = node.delete_url;
      deleteForm.addEventListener('submit', (event) => {
        if (!confirm('Usunąć broń?')) {
          event.preventDefault();
        }
      });
      const deleteButton = document.createElement('button');
      deleteButton.type = 'submit';
      deleteButton.className = 'btn btn-outline-danger';
      deleteButton.textContent = 'Usuń';
      deleteForm.appendChild(deleteButton);
      group.appendChild(deleteForm);

      actionsCol.appendChild(group);
    } else {
      const readonly = document.createElement('span');
      readonly.className = 'text-muted small';
      readonly.textContent = 'Tylko podgląd';
      actionsCol.appendChild(readonly);
    }

    if (filterQuery && !node._matches && node._visibleChildren > 0) {
      row.classList.add('text-muted');
    }

    row.appendChild(nameCol);
    row.appendChild(rangeCol);
    row.appendChild(attacksCol);
    row.appendChild(apCol);
    row.appendChild(abilitiesCol);
    row.appendChild(costCol);
    row.appendChild(actionsCol);
    treeBody.appendChild(row);
    rows.push(row);

    const showChildren = Array.isArray(node.children) && node.children.length && (filterQuery ? true : isExpanded);
    if (showChildren) {
      node.children.forEach((child) => {
        renderNode(child, rows);
      });
    }
  };

  const renderTree = (visibleCount) => {
    if (!treeBody) {
      return;
    }
    treeBody.innerHTML = '';
    sortButtons.forEach((button) => {
      button.disabled = !treeData.length;
    });
    if (!treeData.length) {
      if (filterInput) {
        filterInput.disabled = true;
        filterInput.placeholder = 'Brak pozycji do filtrowania';
      }
      if (emptyState) {
        emptyState.classList.remove('d-none');
      }
      if (filterEmptyState) {
        filterEmptyState.classList.add('d-none');
      }
      return;
    }
    if (filterInput && filterInput.disabled) {
      filterInput.disabled = false;
      filterInput.placeholder = 'Wpisz nazwę, zdolność lub inną cechę';
    }
    if (filterQuery && visibleCount === 0) {
      if (filterEmptyState) {
        filterEmptyState.classList.remove('d-none');
      }
      if (emptyState) {
        emptyState.classList.add('d-none');
      }
      return;
    }
    if (emptyState) {
      emptyState.classList.add('d-none');
    }
    if (filterEmptyState) {
      filterEmptyState.classList.add('d-none');
    }
    const rows = [];
    highlightRow = null;
    treeData.forEach((node) => {
      renderNode(node, rows);
    });
    if (rows.length) {
      rows[rows.length - 1].classList.remove('border-bottom');
    }

    if (highlightRow && highlightScrollPending) {
      highlightScrollPending = false;
      if (typeof highlightRow.scrollIntoView === 'function') {
        requestAnimationFrame(() => {
          highlightRow.scrollIntoView({ block: 'center' });
        });
      }
    }
  };

  const applyFilterAndRender = () => {
    applySort();
    const visibleCount = computeVisibility(treeData);
    renderTree(visibleCount);
    updateSortIndicators();
  };

  sortButtons.forEach((button) => {
    const sortKey = button.dataset.sortKey;
    const sortType = button.dataset.sortType || 'text';
    button.addEventListener('click', (event) => {
      event.preventDefault();
      if (!treeData.length) {
        return;
      }
      let nextDirection = 'asc';
      if (sortState.key === sortKey) {
        nextDirection = sortState.direction === 'asc' ? 'desc' : sortState.direction === 'desc' ? 'none' : 'asc';
      }
      sortState.key = nextDirection === 'none' ? null : sortKey;
      sortState.direction = nextDirection;
      sortState.type = sortType;
      applyFilterAndRender();
    });
  });

  if (filterInput) {
    filterInput.addEventListener('input', () => {
      filterQuery = normalizeText(filterInput.value || '');
      applyFilterAndRender();
    });
  }

  applyFilterAndRender();
}

document.addEventListener('DOMContentLoaded', () => {
  initAbilityPickers();
  initNumberPickers();
  initRangePickers();
  initWeaponPickers();
  initRosterEditor();
  initWeaponDefaults();
  initSpellAbilityForms();
  initArmoryWeaponTree();
});
