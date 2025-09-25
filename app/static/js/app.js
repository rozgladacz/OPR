function initAbilityPicker(root) {
  const definitionsData = root.dataset.definitions;
  const definitions = definitionsData ? JSON.parse(definitionsData) : [];
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
    const isDefault = allowDefaultToggle ? Boolean(entry.is_default ?? defaultInitial) : false;
    return {
      slug,
      value: rawValue,
      raw: rawLabel || rawValue || label,
      label: label || rawLabel || rawValue,
      ability_id: abilityId,
      is_default: isDefault,
      description: entry.description || descriptionFor({ slug }),
    };
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
    const safeItems = items.map((entry) => ({
      slug: entry.slug,
      value: entry.value,
      label: entry.label,
      raw: entry.raw,
      ability_id: entry.ability_id ?? null,
      is_default: entry.is_default ?? false,
    }));
    hiddenInput.value = JSON.stringify(safeItems);
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
      return;
    }
    const wrapper = document.createElement('div');
    wrapper.className = 'd-flex flex-column gap-2';
    items.forEach((item, index) => {
      const row = document.createElement('div');
      row.className = 'border rounded p-2 d-flex flex-wrap align-items-center gap-2';

      const labelSpan = document.createElement('div');
      labelSpan.className = 'flex-grow-1';
      labelSpan.textContent = item.label || item.raw || item.slug;
      const desc = descriptionFor(item);
      if (desc) {
        labelSpan.title = desc;
      }

      row.appendChild(labelSpan);

      if (allowDefaultToggle) {
        const defaultWrapper = document.createElement('div');
        defaultWrapper.className = 'form-check mb-0';
        const defaultInput = document.createElement('input');
        defaultInput.type = 'checkbox';
        defaultInput.className = 'form-check-input';
        defaultInput.id = `ability-default-${index}-${Math.random().toString(16).slice(2)}`;
        defaultInput.checked = Boolean(item.is_default);
        defaultInput.addEventListener('change', () => {
          item.is_default = defaultInput.checked;
          updateHidden();
        });
        const defaultLabel = document.createElement('label');
        defaultLabel.className = 'form-check-label small';
        defaultLabel.setAttribute('for', defaultInput.id);
        defaultLabel.textContent = 'Domyślna';
        defaultWrapper.appendChild(defaultInput);
        defaultWrapper.appendChild(defaultLabel);
        row.appendChild(defaultWrapper);
      }

      const removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'btn btn-outline-danger btn-sm';
      removeBtn.textContent = 'Usuń';
      removeBtn.addEventListener('click', () => {
        items.splice(index, 1);
        updateHidden();
        renderList();
      });
      row.appendChild(removeBtn);

      wrapper.appendChild(row);
    });
    listEl.appendChild(wrapper);
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

  root.abilityPicker = {
    setItems(newItems) {
      items = Array.isArray(newItems) ? newItems.map((entry) => normalizeEntry(entry || {})) : [];
      updateHidden();
      renderList();
    },
  };
}

function initAbilityPickers() {
  document.querySelectorAll('[data-ability-picker]').forEach((element) => {
    initAbilityPicker(element);
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
      const attacksInput = form.querySelector('#attacks');
      if (attacksInput) {
        attacksInput.value = defaults.attacks || '';
      }
      const apInput = form.querySelector('#ap');
      if (apInput) {
        apInput.value = defaults.ap || '';
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
  const weaponsData = root.dataset.weapons;
  const weapons = weaponsData ? JSON.parse(weaponsData) : [];
  const weaponMap = new Map((weapons || []).map((item) => [String(item.id), item]));
  const targetId = root.dataset.targetInput;
  const hiddenInput = targetId ? document.getElementById(targetId) : root.querySelector('input[type="hidden"]');
  const selectEl = root.querySelector('.weapon-picker-select');
  const defaultCountInput = root.querySelector('.weapon-picker-default-count');
  const addButton = root.querySelector('.weapon-picker-add');
  const listEl = root.querySelector('.weapon-picker-list');
  let items = [];

  function parseInitial() {
    if (!hiddenInput || !hiddenInput.value) {
      items = [];
      return;
    }
    try {
      const parsed = JSON.parse(hiddenInput.value);
      if (Array.isArray(parsed)) {
        items = parsed
          .map((entry) => {
            const rawWeaponId = entry.weapon_id;
            const weaponId = Number.parseInt(rawWeaponId, 10);
            if (!Number.isFinite(weaponId)) {
              return null;
            }
            const name = entry.name || weaponMap.get(String(weaponId))?.name || '';
            const rawCount = entry.count ?? entry.default_count;
            let defaultCount = Number.parseInt(rawCount, 10);
            if (!Number.isFinite(defaultCount)) {
              defaultCount = entry.is_default ? 1 : 0;
            }
            if (defaultCount < 0) {
              defaultCount = 0;
            }
            if (!entry.is_default && entry.is_default !== undefined && defaultCount <= 0) {
              defaultCount = 0;
            }
            return {
              weapon_id: weaponId,
              name: name || weaponMap.get(String(weaponId))?.name || `Broń #${weaponId}`,
              default_count: defaultCount,
            };
          })
          .filter((entry) => entry && entry.weapon_id);
      }
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
        count: entry.default_count,
      }));
      hiddenInput.value = JSON.stringify(payload);
    }
  }

  function ensureUnique(weaponId) {
    return !items.some((entry) => String(entry.weapon_id) === String(weaponId));
  }

  function updateItem(index, changes) {
    const item = items[index];
    if (!item) {
      return;
    }
    items[index] = { ...item, ...changes };
    updateHidden();
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

      const nameSpan = document.createElement('div');
      nameSpan.className = 'flex-grow-1 fw-semibold';
      nameSpan.textContent = item.name || weaponMap.get(String(item.weapon_id))?.name || `Broń #${item.weapon_id}`;

      const defaultGroup = document.createElement('div');
      defaultGroup.className = 'd-flex align-items-center gap-2';
      const defaultLabel = document.createElement('label');
      defaultLabel.className = 'form-label mb-0 small';
      defaultLabel.textContent = 'Domyślna ilość';
      defaultLabel.setAttribute('for', `weapon-default-count-${item.weapon_id}-${index}`);
      const defaultField = document.createElement('input');
      defaultField.className = 'form-control form-control-sm';
      defaultField.type = 'number';
      defaultField.min = '0';
      defaultField.value = Number.isFinite(item.default_count) ? item.default_count : 0;
      defaultField.id = `weapon-default-count-${item.weapon_id}-${index}`;
      defaultField.addEventListener('change', () => {
        const parsed = Number.parseInt(defaultField.value, 10);
        const safeValue = Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
        defaultField.value = safeValue;
        updateItem(index, { default_count: safeValue });
      });
      defaultGroup.appendChild(defaultLabel);
      defaultGroup.appendChild(defaultField);

      const removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'btn btn-outline-danger btn-sm';
      removeBtn.textContent = 'Usuń';
      removeBtn.addEventListener('click', () => {
        items.splice(index, 1);
        updateHidden();
        renderList();
      });

      row.appendChild(nameSpan);
      row.appendChild(defaultGroup);
      row.appendChild(removeBtn);
      wrapper.appendChild(row);
    });
    listEl.appendChild(wrapper);
  }

  function handleAdd() {
    if (!selectEl) {
      return;
    }
    const weaponId = selectEl.value;
    if (!weaponId) {
      return;
    }
    if (!ensureUnique(weaponId)) {
      selectEl.value = '';
      return;
    }
    const weapon = weaponMap.get(String(weaponId));
    const rawCount = defaultCountInput ? Number.parseInt(defaultCountInput.value, 10) : 0;
    const safeCount = Number.isFinite(rawCount) && rawCount >= 0 ? rawCount : 0;
    items.push({
      weapon_id: Number.parseInt(weaponId, 10),
      name: weapon?.name || selectEl.selectedOptions[0]?.textContent || `Broń #${weaponId}`,
      default_count: safeCount,
    });
    updateHidden();
    renderList();
    selectEl.value = '';
    if (defaultCountInput) {
      defaultCountInput.value = '0';
    }
  }

  if (addButton) {
    addButton.addEventListener('click', handleAdd);
  }

  parseInitial();
  renderList();
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

function renderPassiveList(container, items) {
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
  safeItems.forEach((entry) => {
    if (!entry) {
      return;
    }
    const row = document.createElement('div');
    row.className = 'roster-ability-item';
    const label = document.createElement('div');
    label.className = 'roster-ability-label';
    label.textContent = entry.label || entry.raw || '—';
    if (entry.description) {
      label.title = entry.description;
    }
    const cost = document.createElement('div');
    cost.className = 'roster-ability-cost';
    if (entry.cost !== undefined && entry.cost !== null) {
      cost.textContent = `${formatPoints(entry.cost)} pkt/model`;
    } else {
      cost.textContent = 'wliczone';
    }
    row.appendChild(label);
    row.appendChild(cost);
    wrapper.appendChild(row);
  });
  if (!wrapper.childElementCount) {
    return false;
  }
  container.appendChild(wrapper);
  return true;
}

function createLoadoutState(rawLoadout) {
  const state = {
    weapons: new Map(),
    active: new Map(),
    aura: new Map(),
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
  sections.forEach(([section]) => {
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
      const rawId = entry.id ?? entry.weapon_id ?? entry.ability_id;
      if (rawId === undefined || rawId === null) {
        return;
      }
      const parsedId = Number(rawId);
      if (!Number.isFinite(parsedId)) {
        return;
      }
      const rawCount = entry.per_model ?? entry.count ?? 0;
      let parsedCount = Number(rawCount);
      if (!Number.isFinite(parsedCount) || parsedCount < 0) {
        parsedCount = 0;
      }
      state[section].set(parsedId, parsedCount);
    });
  });
  return state;
}

function serializeLoadoutState(state) {
  const result = { weapons: [], active: [], aura: [], mode: 'total' };
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
  return JSON.stringify(result);
}

function ensureStateEntries(map, entries, idKey, defaultKey) {
  const safeEntries = Array.isArray(entries) ? entries : [];
  safeEntries.forEach((entry) => {
    if (!entry) {
      return;
    }
    const rawId = entry[idKey];
    if (rawId === undefined || rawId === null) {
      return;
    }
    const parsedId = Number(rawId);
    if (!Number.isFinite(parsedId)) {
      return;
    }
    let defaultCount = Number(entry[defaultKey] ?? 0);
    if (!Number.isFinite(defaultCount) || defaultCount < 0) {
      defaultCount = 0;
    }
    if (!map.has(parsedId)) {
      map.set(parsedId, defaultCount);
    }
  });
}

function renderAbilityEditor(container, items, stateMap, modelCount, editable, onChange) {
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
  const maxCount = Math.max(Number(modelCount) || 0, 0);
  safeItems.forEach((item) => {
    if (!item || item.ability_id === undefined || item.ability_id === null) {
      return;
    }
    const abilityId = Number(item.ability_id);
    if (!Number.isFinite(abilityId)) {
      return;
    }
    let totalCount = Number(stateMap.get(abilityId));
    if (!Number.isFinite(totalCount) || totalCount < 0) {
      totalCount = Number(item.default_count ?? 0);
      if (!Number.isFinite(totalCount) || totalCount < 0) {
        totalCount = 0;
      }
    }
    if (maxCount > 0 && totalCount > maxCount) {
      totalCount = maxCount;
    }
    stateMap.set(abilityId, totalCount);

    const row = document.createElement('div');
    row.className = 'roster-ability-item';

    const info = document.createElement('div');
    info.className = 'roster-ability-details flex-grow-1';
    const name = document.createElement('span');
    name.className = 'roster-ability-label';
    name.textContent = item.label || 'Zdolność';
    if (item.description) {
      name.title = item.description;
    }
    info.appendChild(name);
    const cost = document.createElement('span');
    cost.className = 'roster-ability-cost';
    if (item.cost !== undefined && item.cost !== null) {
      cost.textContent = `+${formatPoints(item.cost)} pkt/model`;
    } else {
      cost.textContent = 'wliczone';
    }
    info.appendChild(cost);
    row.appendChild(info);

    const controls = document.createElement('div');
    controls.className = 'roster-ability-controls text-end';

    const totalLabel = document.createElement('div');
    totalLabel.className = 'text-muted small';
    const updateTotal = (value) => {
      totalLabel.textContent = `Łącznie: ${formatPoints(value)} szt.`;
    };

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
        stateMap.set(abilityId, nextValue);
        updateTotal(nextValue);
        if (typeof onChange === 'function') {
          onChange();
        }
      });
      controls.appendChild(input);
      updateTotal(totalCount);
      controls.appendChild(totalLabel);
    } else {
      updateTotal(totalCount);
      controls.appendChild(totalLabel);
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

function renderWeaponEditor(container, options, stateMap, modelCount, editable, onChange) {
  if (!container) {
    return false;
  }
  container.innerHTML = '';
  const safeOptions = Array.isArray(options) ? options : [];
  if (!safeOptions.length) {
    return false;
  }
  const wrapper = document.createElement('div');
  wrapper.className = 'd-flex flex-column gap-2';
  safeOptions.forEach((option) => {
    if (!option || option.id === undefined || option.id === null) {
      return;
    }
    const weaponId = Number(option.id);
    if (!Number.isFinite(weaponId)) {
      return;
    }
    let totalCount = Number(stateMap.get(weaponId));
    if (!Number.isFinite(totalCount) || totalCount < 0) {
      totalCount = Number(option.default_count ?? 0);
      if (!Number.isFinite(totalCount) || totalCount < 0) {
        totalCount = 0;
      }
    }
    stateMap.set(weaponId, totalCount);

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
    row.appendChild(info);

    const controls = document.createElement('div');
    controls.className = 'roster-ability-controls text-end';
    const totalLabel = document.createElement('div');
    totalLabel.className = 'text-muted small';
    const updateTotal = (value) => {
      totalLabel.textContent = `Łącznie: ${formatPoints(value)} szt.`;
    };

    if (editable) {
      const input = document.createElement('input');
      input.type = 'number';
      input.className = 'form-control form-control-sm roster-count-input';
      input.min = '0';
      input.value = String(totalCount);
      input.addEventListener('change', () => {
        let nextValue = Number(input.value);
        if (!Number.isFinite(nextValue) || nextValue < 0) {
          nextValue = 0;
        }
        input.value = String(nextValue);
        stateMap.set(weaponId, nextValue);
        updateTotal(nextValue);
        if (typeof onChange === 'function') {
          onChange();
        }
      });
      controls.appendChild(input);
      updateTotal(totalCount);
      controls.appendChild(totalLabel);
    } else {
      updateTotal(totalCount);
      controls.appendChild(totalLabel);
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

function computeTotalCost(basePerModel, modelCount, weaponOptions, state, abilityCostMap) {
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
  const safeOptions = Array.isArray(weaponOptions) ? weaponOptions : [];
  safeOptions.forEach((option) => {
    if (!option || option.id === undefined || option.id === null) {
      return;
    }
    const weaponId = Number(option.id);
    const costValue = Number(option.cost);
    if (Number.isFinite(weaponId) && Number.isFinite(costValue)) {
      weaponCostMap.set(weaponId, costValue);
    }
  });

  if (state && state.weapons instanceof Map) {
    state.weapons.forEach((value, weaponId) => {
      const totalCount = toTotal(value);
      if (totalCount <= 0) {
        return;
      }
      const costValue = weaponCostMap.get(weaponId);
      if (costValue !== undefined) {
        total += costValue * totalCount;
      }
    });
  }

  if (state) {
    [state.active, state.aura].forEach((section) => {
      if (!(section instanceof Map)) {
        return;
      }
      section.forEach((value, abilityId) => {
        const totalCount = toTotal(value);
        if (totalCount <= 0) {
          return;
        }
        const costValue = abilityCostMap.get(abilityId);
        if (costValue !== undefined) {
          total += costValue * totalCount;
        }
      });
    });
  }

  return total;
}

function initRosterEditor() {
  const root = document.querySelector('[data-roster-root]');
  if (!root) {
    return;
  }
  const rosterId = root.dataset.rosterId || '';
  const items = Array.from(root.querySelectorAll('[data-roster-item]'));
  const editor = root.querySelector('[data-roster-editor]');
  const emptyState = root.querySelector('[data-roster-editor-empty]');
  const nameEl = root.querySelector('[data-roster-editor-name]');
  const statsEl = root.querySelector('[data-roster-editor-stats]');
  const passiveContainer = root.querySelector('[data-roster-editor-passives]');
  const activeContainer = root.querySelector('[data-roster-editor-actives]');
  const auraContainer = root.querySelector('[data-roster-editor-auras]');
  const loadoutContainer = root.querySelector('[data-roster-editor-loadout]');
  const form = root.querySelector('[data-roster-editor-form]');
  const deleteForm = root.querySelector('[data-roster-editor-delete]');
  const countInput = root.querySelector('[data-roster-editor-count]');
  const loadoutInput = root.querySelector('[data-roster-editor-loadout-input]');
  const costValueEl = root.querySelector('[data-roster-editor-cost]');
  const costDisplayEl = root.querySelector('[data-roster-editor-cost-display]');
  const costBadgeEl = root.querySelector('[data-roster-editor-cost-badge]');
  const isEditable = Boolean(form && countInput && loadoutInput);

  let activeItem = null;
  let loadoutState = createLoadoutState({});
  let currentCount = 1;
  let currentWeapons = [];
  let currentActives = [];
  let currentAuras = [];
  let currentPassives = [];
  let abilityCostMap = new Map();
  let baseCostPerModel = 0;

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

  function buildAbilityCostMap(activeItems, auraItems) {
    const map = new Map();
    [...(Array.isArray(activeItems) ? activeItems : []), ...(Array.isArray(auraItems) ? auraItems : [])].forEach((item) => {
      if (!item || item.ability_id === undefined || item.ability_id === null) {
        return;
      }
      const abilityId = Number(item.ability_id);
      const costValue = Number(item.cost);
      if (Number.isFinite(abilityId) && Number.isFinite(costValue)) {
        map.set(abilityId, costValue);
      }
    });
    return map;
  }

  function updateCostDisplays() {
    const total = computeTotalCost(baseCostPerModel, currentCount, currentWeapons, loadoutState, abilityCostMap);
    const formatted = formatPoints(total);
    if (costValueEl) {
      costValueEl.textContent = formatted;
    }
    if (costDisplayEl) {
      costDisplayEl.textContent = `${formatted} pkt`;
    }
    if (costBadgeEl) {
      costBadgeEl.classList.toggle('d-none', false);
    }
  }

  function handleStateChange() {
    if (loadoutState) {
      loadoutState.mode = 'total';
    }
    if (loadoutInput && loadoutState) {
      loadoutInput.value = serializeLoadoutState(loadoutState);
    }
    updateCostDisplays();
  }

  function renderEditors() {
    const hasPassives = renderPassiveList(passiveContainer, currentPassives);
    toggleSectionVisibility(passiveContainer, hasPassives);
    const hasActives = renderAbilityEditor(
      activeContainer,
      currentActives,
      loadoutState.active,
      currentCount,
      isEditable,
      handleStateChange,
    );
    toggleSectionVisibility(activeContainer, hasActives);
    const hasAuras = renderAbilityEditor(
      auraContainer,
      currentAuras,
      loadoutState.aura,
      currentCount,
      isEditable,
      handleStateChange,
    );
    toggleSectionVisibility(auraContainer, hasAuras);
    const hasWeapons = renderWeaponEditor(
      loadoutContainer,
      currentWeapons,
      loadoutState.weapons,
      currentCount,
      isEditable,
      handleStateChange,
    );
    toggleSectionVisibility(loadoutContainer, hasWeapons);
  }

  function selectItem(item) {
    if (activeItem === item) {
      return;
    }
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
      return;
    }

    currentPassives = parseList(item.getAttribute('data-passives'));
    currentActives = parseList(item.getAttribute('data-actives'));
    currentAuras = parseList(item.getAttribute('data-auras'));
    currentWeapons = parseList(item.getAttribute('data-weapon-options'));

    const unitName = item.getAttribute('data-unit-name') || 'Jednostka';
    const quality = item.getAttribute('data-unit-quality') || '-';
    const defense = item.getAttribute('data-unit-defense') || '-';
    const toughness = item.getAttribute('data-unit-toughness') || '-';
    const countValue = Number(item.getAttribute('data-unit-count') || '1');
    const baseCostValue = Number(item.getAttribute('data-base-cost-per-model') || '0');
    const rosterUnitId = item.getAttribute('data-roster-unit-id');
    const loadoutData = parseLoadout(item.getAttribute('data-loadout'));

    if (nameEl) {
      nameEl.textContent = unitName;
    }
    if (statsEl) {
      statsEl.textContent = `Jakość ${quality} / Obrona ${defense} / Wytrzymałość ${toughness}`;
    }

    currentCount = Number.isFinite(countValue) && countValue >= 1 ? countValue : 1;
    if (countInput) {
      countInput.value = String(currentCount);
    }

    loadoutState = createLoadoutState(loadoutData);
    ensureStateEntries(loadoutState.weapons, currentWeapons, 'id', 'default_count');
    ensureStateEntries(loadoutState.active, currentActives, 'ability_id', 'default_count');
    ensureStateEntries(loadoutState.aura, currentAuras, 'ability_id', 'default_count');
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

    abilityCostMap = buildAbilityCostMap(currentActives, currentAuras);
    baseCostPerModel = Number.isFinite(baseCostValue) && baseCostValue >= 0 ? baseCostValue : 0;

    renderEditors();
    handleStateChange();

    if (form && rosterUnitId) {
      form.setAttribute('action', `/rosters/${rosterId}/units/${rosterUnitId}/update`);
    }
    if (deleteForm && rosterUnitId) {
      deleteForm.setAttribute('action', `/rosters/${rosterId}/units/${rosterUnitId}/delete`);
    }
    editor.classList.remove('d-none');
    emptyState.classList.add('d-none');
  }

  items.forEach((item) => {
    item.addEventListener('click', () => selectItem(item));
  });

  if (countInput) {
    countInput.addEventListener('change', () => {
      let nextValue = Number(countInput.value);
      if (!Number.isFinite(nextValue) || nextValue < 1) {
        nextValue = 1;
        countInput.value = '1';
      }
      currentCount = nextValue;
      renderEditors();
      handleStateChange();
    });
  }

  if (items.length) {
    selectItem(items[0]);
  } else if (editor && emptyState) {
    editor.classList.add('d-none');
    emptyState.classList.remove('d-none');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initAbilityPickers();
  initRangePickers();
  initWeaponPickers();
  initRosterEditor();
  initWeaponDefaults();
});
