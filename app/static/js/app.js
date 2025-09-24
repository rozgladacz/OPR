function initAbilityPicker(root) {
  const definitionsData = root.dataset.definitions;
  const definitions = definitionsData ? JSON.parse(definitionsData) : [];
  const definitionMap = new Map(definitions.map((item) => [item.slug, item]));
  const targetId = root.dataset.targetInput;
  const hiddenInput = targetId ? document.getElementById(targetId) : root.querySelector('input[type="hidden"]');
  const selectEl = root.querySelector('.ability-picker-select');
  const valueContainer = root.querySelector('.ability-picker-value');
  const valueInput = root.querySelector('.ability-picker-value-input');
  const addButton = root.querySelector('.ability-picker-add');
  const listEl = root.querySelector('.ability-picker-list');
  let items = [];

  function parseInitial() {
    if (!hiddenInput || !hiddenInput.value) {
      items = [];
      return;
    }
    try {
      const parsed = JSON.parse(hiddenInput.value);
      if (Array.isArray(parsed)) {
        items = parsed.map((entry) => ({
          slug: entry.slug || '',
          value: entry.value ?? '',
          label: entry.label || '',
          raw: entry.raw || '',
          ability_id: entry.ability_id ?? null,
        }));
      }
    } catch (err) {
      console.warn('Nie udało się odczytać wybranych zdolności', err);
      items = [];
    }
  }

  function updateHidden() {
    if (hiddenInput) {
      const safeItems = items.map((entry) => ({
        slug: entry.slug,
        value: entry.value,
        label: entry.label,
        raw: entry.raw,
        ability_id: entry.ability_id ?? null,
      }));
      hiddenInput.value = JSON.stringify(safeItems);
    }
  }

  function formatLabel(definition, value) {
    if (!definition) {
      return value ? `${value}` : '';
    }
    const trimmed = typeof value === 'string' ? value.trim() : value;
    if (definition.requires_value) {
      if (!trimmed) {
        return definition.display_name;
      }
      return `${definition.name}(${trimmed})`;
    }
    return definition.name;
  }

  function descriptionFor(item) {
    const definition = definitionMap.get(item.slug);
    return definition ? definition.description : '';
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
    wrapper.className = 'd-flex flex-wrap gap-2';
    items.forEach((item, index) => {
      const badge = document.createElement('span');
      badge.className = 'badge text-bg-secondary d-flex align-items-center gap-2';
      const labelSpan = document.createElement('span');
      labelSpan.textContent = item.label || item.raw || item.slug;
      const desc = descriptionFor(item);
      if (desc) {
        badge.title = desc;
      }
      const removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'btn-close btn-close-white btn-close-sm';
      removeBtn.setAttribute('aria-label', 'Usuń');
      removeBtn.addEventListener('click', () => {
        items.splice(index, 1);
        updateHidden();
        renderList();
      });
      badge.appendChild(labelSpan);
      badge.appendChild(removeBtn);
      wrapper.appendChild(badge);
    });
    listEl.appendChild(wrapper);
  }

  function handleSelectChange() {
    if (!selectEl || !valueContainer) {
      return;
    }
    const slug = selectEl.value;
    const definition = definitionMap.get(slug);
    if (definition && definition.requires_value) {
      valueContainer.classList.remove('d-none');
      if (valueInput) {
        valueInput.placeholder = definition.value_label ? `Wartość (${definition.value_label})` : 'Wartość';
      }
    } else {
      valueContainer.classList.add('d-none');
      if (valueInput) {
        valueInput.value = '';
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
    const definition = definitionMap.get(slug);
    const rawValue = valueInput ? valueInput.value || '' : '';
    if (!validateValue(definition, rawValue)) {
      if (valueInput) {
        valueInput.classList.add('is-invalid');
        valueInput.addEventListener(
          'input',
          () => valueInput.classList.remove('is-invalid'),
          { once: true }
        );
      }
      return;
    }
    const label = definition ? formatLabel(definition, rawValue) : (selectEl.selectedOptions[0]?.textContent || slug);
    const entry = {
      slug: definition ? definition.slug : '__custom__',
      value: rawValue.trim(),
      label: label,
      raw: definition ? label : label,
      ability_id: definition && Object.prototype.hasOwnProperty.call(definition, 'ability_id')
        ? definition.ability_id
        : null,
    };
    items.push(entry);
    updateHidden();
    renderList();
    selectEl.value = '';
    if (valueInput) {
      valueInput.value = '';
    }
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
}

function initAbilityPickers() {
  document.querySelectorAll('[data-ability-picker]').forEach((element) => {
    initAbilityPicker(element);
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
  initWeaponPickers();
  initRosterUnitForms();
});
