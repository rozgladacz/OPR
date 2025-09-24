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
      return displayValue ? `${definition.name}(${displayValue})` : definition.display_name;
    }
    if (definition.slug === 'rozkaz') {
      return displayValue ? `${definition.name}(${displayValue})` : definition.display_name;
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
  const defaultToggle = root.querySelector('.weapon-picker-default');
  const countInput = root.querySelector('.weapon-picker-count');
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
          .map((entry) => ({
            weapon_id: entry.weapon_id,
            name: entry.name || (weaponMap.get(String(entry.weapon_id))?.name ?? ''),
            is_default: Boolean(entry.is_default),
            count: Number.parseInt(entry.count, 10) || 1,
          }))
          .filter((entry) => entry.weapon_id);
      }
    } catch (err) {
      console.warn('Nie udało się odczytać listy broni', err);
      items = [];
    }
  }

  function updateHidden() {
    if (hiddenInput) {
      hiddenInput.value = JSON.stringify(items);
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

      const defaultWrapper = document.createElement('div');
      defaultWrapper.className = 'form-check mb-0';
      const defaultInput = document.createElement('input');
      defaultInput.className = 'form-check-input';
      defaultInput.type = 'checkbox';
      defaultInput.checked = Boolean(item.is_default);
      defaultInput.id = `weapon-default-${item.weapon_id}-${index}`;
      defaultInput.addEventListener('change', () => {
        if (!defaultInput.checked) {
          countField.value = '1';
          updateItem(index, { is_default: false, count: 1 });
        } else {
          updateItem(index, { is_default: true });
        }
        countField.disabled = !defaultInput.checked;
      });
      const defaultLabel = document.createElement('label');
      defaultLabel.className = 'form-check-label';
      defaultLabel.setAttribute('for', defaultInput.id);
      defaultLabel.textContent = 'Domyślna';
      defaultWrapper.appendChild(defaultInput);
      defaultWrapper.appendChild(defaultLabel);

      const countGroup = document.createElement('div');
      countGroup.className = 'd-flex align-items-center gap-2';
      const countLabel = document.createElement('label');
      countLabel.className = 'form-label mb-0 small';
      countLabel.textContent = 'Ilość';
      countLabel.setAttribute('for', `weapon-count-${item.weapon_id}-${index}`);
      const countField = document.createElement('input');
      countField.className = 'form-control form-control-sm';
      countField.type = 'number';
      countField.min = '1';
      countField.value = Number.isFinite(item.count) ? item.count : 1;
      countField.id = `weapon-count-${item.weapon_id}-${index}`;
      countField.addEventListener('change', () => {
        const parsed = Number.parseInt(countField.value, 10);
        const safeValue = Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
        countField.value = safeValue;
        updateItem(index, { count: safeValue });
      });
      countField.disabled = !item.is_default;
      countGroup.appendChild(countLabel);
      countGroup.appendChild(countField);

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
      row.appendChild(defaultWrapper);
      row.appendChild(countGroup);
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
    const isDefault = defaultToggle ? defaultToggle.checked : true;
    const countValue = countInput ? Number.parseInt(countInput.value, 10) : 1;
    const safeCount = Number.isFinite(countValue) && countValue > 0 ? countValue : 1;
    items.push({
      weapon_id: Number.parseInt(weaponId, 10),
      name: weapon?.name || selectEl.selectedOptions[0]?.textContent || `Broń #${weaponId}`,
      is_default: isDefault,
      count: safeCount,
    });
    updateHidden();
    renderList();
    selectEl.value = '';
    if (defaultToggle) {
      defaultToggle.checked = true;
    }
    if (countInput) {
      countInput.value = '1';
      countInput.disabled = false;
    }
  }

  if (addButton) {
    addButton.addEventListener('click', handleAdd);
  }

  if (defaultToggle && countInput) {
    const syncAddControls = () => {
      if (!defaultToggle.checked) {
        countInput.value = '1';
      }
      countInput.disabled = !defaultToggle.checked;
    };
    defaultToggle.addEventListener('change', syncAddControls);
    syncAddControls();
  }

  parseInitial();
  renderList();
}

function initWeaponPickers() {
  document.querySelectorAll('[data-weapon-picker]').forEach((element) => {
    initWeaponPicker(element);
  });
}

function parseWeaponOptions(optionEl) {
  if (!optionEl) {
    return { weapons: [], summary: '-' };
  }
  const rawWeapons = optionEl.getAttribute('data-weapons');
  let weapons = [];
  if (rawWeapons) {
    try {
      const parsed = JSON.parse(rawWeapons);
      if (Array.isArray(parsed)) {
        weapons = parsed.map((item) => ({ id: String(item.id ?? ''), name: item.name || '' }));
      }
    } catch (err) {
      console.warn('Nie udało się odczytać listy broni dla jednostki', err);
    }
  }
  const summary = optionEl.getAttribute('data-default-summary') || '-';
  return { weapons, summary };
}

function initRosterUnitForm(form) {
  const unitSelect = form.querySelector('[data-roster-unit-select]');
  const weaponSelect = form.querySelector('[data-roster-weapon-select]');
  const defaultSummaryEl = form.querySelector('[data-roster-default-summary]');
  if (!weaponSelect) {
    return;
  }
  const placeholder = weaponSelect.dataset.placeholder || 'Domyślne wyposażenie';

  const updateSummary = (summary) => {
    if (!defaultSummaryEl) {
      return;
    }
    if (summary && summary !== '-' && summary.trim() !== '') {
      defaultSummaryEl.textContent = `Domyślne wyposażenie: ${summary}`;
    } else {
      defaultSummaryEl.textContent = 'Brak domyślnego uzbrojenia.';
    }
  };

  const populateWeapons = (weapons, summary, selectedValue) => {
    weaponSelect.innerHTML = '';
    const defaultOption = document.createElement('option');
    defaultOption.value = '';
    defaultOption.textContent = summary && summary !== '-' && summary.trim() !== '' ? `${placeholder} (${summary})` : placeholder;
    weaponSelect.appendChild(defaultOption);
    weapons.forEach((weapon) => {
      const option = document.createElement('option');
      option.value = String(weapon.id || '');
      option.textContent = weapon.name || `Broń #${weapon.id}`;
      weaponSelect.appendChild(option);
    });
    if (selectedValue && weapons.some((weapon) => String(weapon.id) === String(selectedValue))) {
      weaponSelect.value = String(selectedValue);
    } else {
      weaponSelect.value = '';
    }
    weaponSelect.disabled = false;
    updateSummary(summary);
    weaponSelect.removeAttribute('data-selected');
  };

  if (unitSelect) {
    const syncFromSelection = () => {
      const option = unitSelect.selectedOptions[0];
      const { weapons, summary } = parseWeaponOptions(option);
      populateWeapons(weapons, summary, weaponSelect.dataset.selected || '');
    };
    unitSelect.addEventListener('change', () => {
      weaponSelect.dataset.selected = '';
      syncFromSelection();
    });
    syncFromSelection();
  } else {
    const selectedValue = weaponSelect.dataset.selected || '';
    if (selectedValue) {
      weaponSelect.value = selectedValue;
      weaponSelect.removeAttribute('data-selected');
    }
  }
}

function initRosterUnitForms() {
  document.querySelectorAll('[data-roster-unit-form]').forEach((form) => {
    initRosterUnitForm(form);
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initAbilityPickers();
  initRangePickers();
  initWeaponPickers();
  initRosterUnitForms();
  initWeaponDefaults();
});
