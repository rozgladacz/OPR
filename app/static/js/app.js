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

function renderAbilityList(container, items, emptyText) {
  if (!container) {
    return;
  }
  container.innerHTML = '';
  const safeItems = Array.isArray(items) ? items : [];
  if (!safeItems.length) {
    const empty = document.createElement('span');
    empty.className = 'text-muted small';
    empty.textContent = emptyText;
    container.appendChild(empty);
    return;
  }
  const wrapper = document.createElement('div');
  wrapper.className = 'd-flex flex-column gap-2';
  safeItems.forEach((entry) => {
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
      cost.textContent = `${formatPoints(entry.cost)} pkt`; 
    } else {
      cost.textContent = 'wliczone';
    }
    row.appendChild(label);
    row.appendChild(cost);
    wrapper.appendChild(row);
  });
  container.appendChild(wrapper);
}

function updateLoadout(container, selectEl, defaultSummary) {
  if (!container) {
    return;
  }
  container.innerHTML = '';
  const row = document.createElement('div');
  row.className = 'roster-ability-item';
  const label = document.createElement('div');
  label.className = 'roster-ability-label';
  const cost = document.createElement('div');
  cost.className = 'roster-ability-cost';
  if (selectEl && selectEl.value) {
    const option = selectEl.selectedOptions[0];
    label.textContent = option ? option.textContent : 'Wybrana broń';
    const rawCost = option ? option.getAttribute('data-cost') : null;
    if (rawCost !== null && rawCost !== undefined && rawCost !== '') {
      cost.textContent = `+${formatPoints(rawCost)} pkt / model`;
    } else {
      cost.textContent = 'wliczone';
    }
  } else {
    const summary = defaultSummary && defaultSummary.trim() !== '' ? defaultSummary : 'Domyślne wyposażenie';
    label.textContent = `Domyślne: ${summary}`;
    cost.textContent = 'wliczone';
  }
  row.appendChild(label);
  row.appendChild(cost);
  container.appendChild(row);
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
  const weaponSelect = root.querySelector('[data-roster-editor-weapon]');
  const defaultHint = root.querySelector('[data-roster-editor-default]');
  const costEl = root.querySelector('[data-roster-editor-cost]');
  let activeItem = null;
  let currentDefaultSummary = '';

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

  function populateWeapons(options, selectedId, defaultSummary) {
    if (!weaponSelect) {
      return;
    }
    weaponSelect.innerHTML = '';
    const placeholder = document.createElement('option');
    placeholder.value = '';
    const summaryText = defaultSummary && defaultSummary.trim() !== '' ? `${defaultSummary}` : 'Domyślne wyposażenie';
    placeholder.textContent = `Domyślne (${summaryText})`;
    weaponSelect.appendChild(placeholder);
    const safeOptions = Array.isArray(options) ? options : [];
    safeOptions.forEach((weapon) => {
      const option = document.createElement('option');
      option.value = weapon.id !== undefined && weapon.id !== null ? String(weapon.id) : '';
      const costLabel = weapon.cost !== undefined && weapon.cost !== null ? ` (+${formatPoints(weapon.cost)} pkt/model)` : '';
      option.textContent = `${weapon.name || 'Broń'}${costLabel}`;
      if (weapon.cost !== undefined && weapon.cost !== null) {
        option.setAttribute('data-cost', weapon.cost);
      }
      weaponSelect.appendChild(option);
    });
    const matched = safeOptions.some((weapon) => String(weapon.id) === String(selectedId));
    if (selectedId && matched) {
      weaponSelect.value = String(selectedId);
    } else {
      weaponSelect.value = '';
    }
    if (defaultHint) {
      defaultHint.textContent = summaryText && summaryText !== '-' ? `Domyślne uzbrojenie: ${summaryText}` : 'Brak domyślnego uzbrojenia.';
    }
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

    const passives = parseList(item.getAttribute('data-passives'));
    const actives = parseList(item.getAttribute('data-actives'));
    const auras = parseList(item.getAttribute('data-auras'));
    const weapons = parseList(item.getAttribute('data-weapon-options'));
    const defaultSummary = item.getAttribute('data-default-summary') || '';
    const selectedWeaponId = item.getAttribute('data-selected-weapon-id') || '';
    const unitName = item.getAttribute('data-unit-name') || 'Jednostka';
    const quality = item.getAttribute('data-unit-quality') || '-';
    const defense = item.getAttribute('data-unit-defense') || '-';
    const toughness = item.getAttribute('data-unit-toughness') || '-';
    const count = item.getAttribute('data-unit-count') || '1';
    const costValue = item.getAttribute('data-unit-cost') || '0';
    const rosterUnitId = item.getAttribute('data-roster-unit-id');

    if (nameEl) {
      nameEl.textContent = unitName;
    }
    if (statsEl) {
      statsEl.textContent = `Jakość ${quality} / Obrona ${defense} / Wytrzymałość ${toughness}`;
    }
    renderAbilityList(passiveContainer, passives, 'Brak zdolności.');
    renderAbilityList(activeContainer, actives, 'Brak zdolności.');
    renderAbilityList(auraContainer, auras, 'Brak aur.');
    populateWeapons(weapons, selectedWeaponId, defaultSummary);
    updateLoadout(loadoutContainer, weaponSelect, defaultSummary);
    currentDefaultSummary = defaultSummary;

    if (countInput) {
      countInput.value = count;
    }
    if (costEl) {
      costEl.textContent = formatPoints(costValue);
    }
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

  if (weaponSelect) {
    weaponSelect.addEventListener('change', () => {
      updateLoadout(loadoutContainer, weaponSelect, currentDefaultSummary);
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
