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

function renderPassiveEditor(container, items, stateMap, modelCount, editable, onChange) {
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
    let currentValue = Number(stateMap.get(slug));
    if (!Number.isFinite(currentValue)) {
      currentValue = Number(entry.default_count ?? (entry.is_default ? 1 : 0));
    }
    if (!Number.isFinite(currentValue) || currentValue <= 0) {
      currentValue = 0;
    } else {
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
    const defaultFlag = Number(entry.default_count ?? (entry.is_default ? 1 : 0)) > 0 ? 1 : 0;
    const computeDeltaText = (selectedFlag) => {
      if (!Number.isFinite(costValue) || costValue === 0) {
        return 'Δ 0 pkt';
      }
      const diff = selectedFlag - defaultFlag;
      if (diff === 0) {
        return 'Δ 0 pkt';
      }
      const multiplier = Math.max(totalModels, 1);
      const delta = costValue * diff * multiplier;
      const prefix = delta > 0 ? '+' : '';
      return `Δ ${prefix}${formatPoints(delta)} pkt`;
    };
    let currentFlag = currentValue > 0 ? 1 : 0;
    cost.textContent = computeDeltaText(currentFlag);
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
      const label = document.createElement('label');
      label.className = 'form-check-label small';
      label.setAttribute('for', input.id);
      label.textContent = input.checked ? 'Aktywna' : 'Wyłączona';
      const updateLabel = () => {
        label.textContent = input.checked ? 'Aktywna' : 'Wyłączona';
      };
      input.addEventListener('change', () => {
        const flag = input.checked ? 1 : 0;
        stateMap.set(slug, flag);
        currentFlag = flag;
        cost.textContent = computeDeltaText(currentFlag);
        updateLabel();
        if (typeof onChange === 'function') {
          onChange();
        }
      });
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

function createLoadoutState(rawLoadout) {
  const state = {
    weapons: new Map(),
    active: new Map(),
    aura: new Map(),
    passive: new Map(),
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
  return state;
}

function serializeLoadoutState(state) {
  const result = { weapons: [], active: [], aura: [], passive: [], mode: 'total' };
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
      input.addEventListener('change', () => {
        let nextValue = Number(input.value);
        if (!Number.isFinite(nextValue) || nextValue < 0) {
          nextValue = 0;
        }
        input.value = String(nextValue);
        stateMap.set(weaponId, nextValue);
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

function computeTotalCost(basePerModel, modelCount, weaponOptions, state, costMaps, passiveItems) {
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
      const costValue = activeCostMap.get(Number(abilityId));
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
  root.querySelectorAll('[data-roster-add-trigger]').forEach((trigger) => {
    const form = trigger.closest('form');
    if (!form) {
      return;
    }
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
    const success = document.createElement('div');
    success.className = 'alert alert-success mb-0';
    success.textContent = 'Brak ostrzeżeń.';
    container.appendChild(success);
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
  const duplicateForm = root.querySelector('[data-roster-editor-duplicate]');
  const deleteForm = root.querySelector('[data-roster-editor-delete]');
  const countInput = root.querySelector('[data-roster-editor-count]');
  const customNameInput = root.querySelector('[data-roster-editor-custom-name]');
  const customLabel = root.querySelector('[data-roster-editor-custom-label]');
  const loadoutInput = root.querySelector('[data-roster-editor-loadout-input]');
  const costValueEl = root.querySelector('[data-roster-editor-cost]');
  const costDisplayEl = root.querySelector('[data-roster-editor-cost-display]');
  const costBadgeEl = root.querySelector('[data-roster-editor-cost-badge]');
  const saveStateEl = root.querySelector('[data-roster-editor-save-state]');
  const totalContainer = root.querySelector('[data-roster-total-container]');
  const totalValueEl = root.querySelector('[data-roster-total]');
  const warningsContainer = root.querySelector('[data-roster-warnings]');
  const isEditable = Boolean(form && countInput && loadoutInput);

  if (warningsContainer) {
    try {
      const initialWarnings = JSON.parse(warningsContainer.dataset.warnings || '[]');
      renderWarningsList(warningsContainer, Array.isArray(initialWarnings) ? initialWarnings : []);
    } catch (err) {
      renderWarningsList(warningsContainer, []);
    }
  }

  let activeItem = null;
  let loadoutState = createLoadoutState({});
  let currentCount = 1;
  let currentWeapons = [];
  let currentActives = [];
  let currentAuras = [];
  let currentPassives = [];
  let abilityCostMap = { active: new Map(), passive: new Map() };
  let baseCostPerModel = 0;
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

  function syncDefaultEquipment(previousCount, nextCount) {
    if (!loadoutState) {
      return;
    }
    const prev = Math.max(Number(previousCount) || 0, 0);
    const next = Math.max(Number(nextCount) || 0, 0);
    if (prev === next) {
      return;
    }
    const adjust = (map, items, idKey) => {
      if (!(map instanceof Map)) {
        return;
      }
      const safeItems = Array.isArray(items) ? items : [];
      safeItems.forEach((item) => {
        if (!item) {
          return;
        }
        const rawId = item[idKey];
        if (rawId === undefined || rawId === null) {
          return;
        }
        const numericId = Number(rawId);
        if (!Number.isFinite(numericId)) {
          return;
        }
        const defaultValue = Number(item.default_count ?? 0);
        if (!Number.isFinite(defaultValue) || defaultValue <= 0) {
          return;
        }
        const prevTotal = prev * defaultValue;
        const stored = Number(map.get(numericId));
        const diff = Number.isFinite(stored) ? stored - prevTotal : 0;
        const nextTotal = Math.max(next * defaultValue + diff, 0);
        map.set(numericId, nextTotal);
      });
    };
    adjust(loadoutState.weapons, currentWeapons, 'id');
    adjust(loadoutState.active, currentActives, 'ability_id');
    adjust(loadoutState.aura, currentAuras, 'ability_id');
  }

  function buildAbilityCostMap(activeItems, auraItems, passiveItems) {
    const activeMap = new Map();
    const passiveMap = new Map();
    [...(Array.isArray(activeItems) ? activeItems : []), ...(Array.isArray(auraItems) ? auraItems : [])].forEach((item) => {
      if (!item || item.ability_id === undefined || item.ability_id === null) {
        return;
      }
      const abilityId = Number(item.ability_id);
      const costValue = Number(item.cost);
      if (Number.isFinite(abilityId) && Number.isFinite(costValue)) {
        activeMap.set(abilityId, costValue);
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
      if (typeof unitData.custom_name === 'string') {
        targetItem.setAttribute('data-unit-custom-name', unitData.custom_name);
      }
      if (typeof unitData.loadout_json === 'string') {
        targetItem.setAttribute('data-loadout', unitData.loadout_json);
      }
      const unitName = targetItem.getAttribute('data-unit-name') || 'Jednostka';
      if (typeof unitData.count === 'number' && Number.isFinite(unitData.count)) {
        const titleEl = targetItem.querySelector('[data-roster-unit-title]');
        if (titleEl) {
          titleEl.textContent = `${unitData.count}x ${unitName}`;
        }
      }
      const customEl = targetItem.querySelector('[data-roster-unit-custom]');
      if (customEl) {
        if (unitData.custom_name) {
          customEl.textContent = unitData.custom_name;
          customEl.classList.remove('d-none');
        } else {
          customEl.textContent = '';
          customEl.classList.add('d-none');
        }
      }
      const costBadge = targetItem.querySelector('[data-roster-unit-cost]');
      if (costBadge && typeof unitData.cached_cost === 'number') {
        costBadge.textContent = `${formatPoints(unitData.cached_cost)} pkt`;
      }
      const loadoutEl = targetItem.querySelector('[data-roster-unit-loadout]');
      if (loadoutEl) {
        const defaultSummary = targetItem.getAttribute('data-default-summary') || '-';
        const summary = unitData.loadout_summary || defaultSummary;
        loadoutEl.textContent = `Uzbrojenie: ${summary || '-'}`;
      }
      if (isActiveMatch) {
        ignoreNextSave = true;
        selectItem(targetItem, { preserveAutoSave: true });
      }
    }
    if (payload.roster && typeof payload.roster.total_cost === 'number') {
      updateTotalSummary(payload.roster.total_cost);
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
    );
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
    if (activeItem) {
      activeItem.setAttribute('data-unit-cost', String(total));
      const listBadge = activeItem.querySelector('[data-roster-unit-cost]');
      if (listBadge) {
        listBadge.textContent = `${formatted} pkt`;
      }
    }
    return total;
  }

  function handleStateChange() {
    if (loadoutState) {
      loadoutState.mode = 'total';
    }
    if (loadoutInput && loadoutState) {
      loadoutInput.value = serializeLoadoutState(loadoutState);
    }
    updateCostDisplays();
    if (activeItem && loadoutInput) {
      activeItem.setAttribute('data-loadout', loadoutInput.value || '{}');
    }
    if (activeItem) {
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

  function renderEditors() {
    const hasPassives = renderPassiveEditor(
      passiveContainer,
      currentPassives,
      loadoutState.passive,
      currentCount,
      isEditable,
      handleStateChange,
    );
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
      if (customLabel) {
        customLabel.textContent = '';
        customLabel.classList.add('d-none');
      }
      autoSaveEnabled = false;
      setSaveStatus('idle');
      return;
    }

    if (!preserveAutoSave) {
      autoSaveEnabled = false;
      setSaveStatus('idle');
    } else if (!isEditable) {
      autoSaveEnabled = false;
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
    const customName = item.getAttribute('data-unit-custom-name') || '';

    if (nameEl) {
      nameEl.textContent = unitName;
    }
    if (statsEl) {
      statsEl.textContent = `Jakość ${quality} / Obrona ${defense} / Wytrzymałość ${toughness}`;
    }
    if (customNameInput) {
      customNameInput.value = customName;
    }
    if (customLabel) {
      if (customName) {
        customLabel.textContent = `Nazwa oddziału: ${customName}`;
        customLabel.classList.remove('d-none');
      } else {
        customLabel.textContent = '';
        customLabel.classList.add('d-none');
      }
    }

    currentCount = Number.isFinite(countValue) && countValue >= 1 ? countValue : 1;
    if (countInput) {
      countInput.value = String(currentCount);
    }

    loadoutState = createLoadoutState(loadoutData);
    ensureStateEntries(loadoutState.weapons, currentWeapons, 'id', 'default_count');
    ensureStateEntries(loadoutState.active, currentActives, 'ability_id', 'default_count');
    ensureStateEntries(loadoutState.aura, currentAuras, 'ability_id', 'default_count');
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
    renderEditors();
    handleStateChange();

    if (form && rosterUnitId) {
      form.setAttribute('action', `/rosters/${rosterId}/units/${rosterUnitId}/update`);
    }
    if (duplicateForm && rosterUnitId) {
      duplicateForm.setAttribute('action', `/rosters/${rosterId}/units/${rosterUnitId}/duplicate`);
    }
    if (deleteForm && rosterUnitId) {
      deleteForm.setAttribute('action', `/rosters/${rosterId}/units/${rosterUnitId}/delete`);
    }
    editor.classList.remove('d-none');
    emptyState.classList.add('d-none');
    autoSaveEnabled = isEditable;
    setSaveStatus(currentSaveStatus);
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
      syncDefaultEquipment(currentCount, nextValue);
      currentCount = nextValue;
      renderEditors();
      handleStateChange();
    });
  }

  if (customNameInput && customLabel) {
    customNameInput.addEventListener('input', () => {
      const rawValue = customNameInput.value || '';
      const value = rawValue.trim();
      if (value) {
        customLabel.textContent = `Nazwa oddziału: ${value}`;
        customLabel.classList.remove('d-none');
      } else {
        customLabel.textContent = '';
        customLabel.classList.add('d-none');
      }
      if (activeItem) {
        activeItem.setAttribute('data-unit-custom-name', rawValue);
      }
      if (autoSaveEnabled) {
        setSaveStatus('dirty');
        scheduleSave();
      }
    });
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

document.addEventListener('DOMContentLoaded', () => {
  initAbilityPickers();
  initRangePickers();
  initWeaponPickers();
  initRosterEditor();
  initWeaponDefaults();
});
