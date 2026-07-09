(function () {
    const ENHANCED_ATTR = 'data-select-search-enhanced';
    const WRAPPER_CLASS = 'select-search';
    const CUSTOM_VALUE_ATTR = 'data-allow-custom';

    function normalize(value) {
        return String(value || '').trim().toLowerCase();
    }

    function escapeHtml(value) {
        return String(value || '').replace(/[&<>"']/g, function (ch) {
            return {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#39;'
            }[ch];
        });
    }

    function optionText(option) {
        return String(option.textContent || '').trim();
    }

    function optionSearchText(option) {
        return normalize([
            optionText(option),
            option.value,
            option.getAttribute('data-code'),
            option.getAttribute('data-name'),
            option.getAttribute('data-specification'),
            option.getAttribute('data-spec'),
            option.getAttribute('data-model'),
            option.getAttribute('data-unit'),
            option.getAttribute('data-search')
        ].filter(Boolean).join(' '));
    }

    function optionMeta(option) {
        return [
            option.getAttribute('data-code'),
            option.getAttribute('data-name'),
            option.getAttribute('data-specification') || option.getAttribute('data-spec'),
            option.getAttribute('data-unit')
        ].filter(Boolean).join(' / ');
    }

    function optionDisplayText(option) {
        return optionMeta(option) || optionText(option);
    }

    function isIdSelect(select) {
        const name = select.getAttribute('name') || '';
        return /(^|_|\[)id(\]?$|_|\[)|_id(\[\])?$/.test(name) || name.endsWith('_id[]');
    }

    function canUseCustomValue(select) {
        if (select.hasAttribute(CUSTOM_VALUE_ATTR)) return select.getAttribute(CUSTOM_VALUE_ATTR) !== 'false';
        return !isIdSelect(select);
    }

    function selectedLabel(select) {
        const option = select.options[select.selectedIndex];
        return option && option.value !== '' ? optionDisplayText(option) : '';
    }

    function visibleOptions(select, query) {
        const needle = normalize(query);
        return Array.from(select.options).filter(function (option) {
            if (!option.value && !needle) return false;
            if (!option.value && needle) return false;
            return !needle || optionSearchText(option).indexOf(needle) >= 0;
        }).slice(0, 80);
    }

    function setSelectValue(select, option, input, list) {
        select.value = option ? option.value : '';
        input.value = option ? optionDisplayText(option) : '';
        select.dispatchEvent(new Event('change', { bubbles: true }));
        closeList(list);
    }

    function closeList(list) {
        list.hidden = true;
        list.innerHTML = '';
    }

    function positionList(input, list) {
        if (!list || list.hidden) return;
        const rect = input.getBoundingClientRect();
        list.style.left = rect.left + 'px';
        list.style.top = (rect.bottom + 4) + 'px';
        list.style.width = Math.max(rect.width, 320) + 'px';
    }

    function renderList(select, input, list) {
        const query = input.value;
        const options = visibleOptions(select, query);
        if (!options.length) {
            list.innerHTML = '<div class="select-search-empty">无匹配项</div>';
            list.hidden = false;
            return;
        }
        list.innerHTML = options.map(function (option, index) {
            const active = option.value === select.value ? ' active' : '';
            return '<button type="button" class="select-search-option' + active + '" data-index="' + index + '">' +
                escapeHtml(optionDisplayText(option)) +
                '</button>';
        }).join('');
        list.hidden = false;
        positionList(input, list);
        Array.from(list.querySelectorAll('.select-search-option')).forEach(function (button) {
            button.addEventListener('mousedown', function (event) {
                event.preventDefault();
                const option = options[Number(button.getAttribute('data-index'))];
                setSelectValue(select, option, input, list);
            });
        });
    }

    function commitInput(select, input, list) {
        const text = input.value.trim();
        if (!text) {
            select.value = '';
            select.dispatchEvent(new Event('change', { bubbles: true }));
            closeList(list);
            return;
        }

        const exact = Array.from(select.options).find(function (option) {
            return option.value && (
                normalize(optionText(option)) === normalize(text)
                || normalize(optionDisplayText(option)) === normalize(text)
                || normalize(option.value) === normalize(text)
                || normalize(option.getAttribute('data-code')) === normalize(text)
                || normalize(option.getAttribute('data-name')) === normalize(text)
            );
        });
        if (exact) {
            setSelectValue(select, exact, input, list);
            return;
        }

        const matches = visibleOptions(select, text);
        if (matches.length === 1) {
            setSelectValue(select, matches[0], input, list);
            return;
        }

        if (canUseCustomValue(select)) {
            let custom = Array.from(select.options).find(function (option) {
                return option.value === text;
            });
            if (!custom) {
                custom = new Option(text, text, true, true);
                custom.setAttribute('data-custom', 'true');
                select.add(custom);
            }
            setSelectValue(select, custom, input, list);
            return;
        }

        input.value = selectedLabel(select);
        closeList(list);
    }

    function enhanceSelect(select) {
        if (!select || select.getAttribute(ENHANCED_ATTR) === 'true') return;
        if (select.multiple || select.disabled || select.classList.contains('d-none')) return;
        if (select.closest('.select-search')) return;
        if (select.closest('[data-no-select-search]')) return;

        select.setAttribute(ENHANCED_ATTR, 'true');
        const wrapper = document.createElement('div');
        wrapper.className = WRAPPER_CLASS;
        const input = document.createElement('input');
        input.type = 'text';
        input.className = select.classList.contains('form-select-sm')
            ? 'form-control form-control-sm select-search-input'
            : 'form-control select-search-input';
        input.placeholder = select.options[0] && !select.options[0].value ? optionText(select.options[0]) : '输入关键字匹配';
        input.value = selectedLabel(select);
        input.autocomplete = 'off';
        if (select.required) input.required = true;

        const list = document.createElement('div');
        list.className = 'select-search-list';
        list.hidden = true;

        select.classList.add('select-search-source');
        select.tabIndex = -1;
        select.parentNode.insertBefore(wrapper, select);
        wrapper.appendChild(select);
        wrapper.appendChild(input);
        document.body.appendChild(list);

        input.addEventListener('focus', function () {
            renderList(select, input, list);
        });
        input.addEventListener('input', function () {
            renderList(select, input, list);
        });
        input.addEventListener('keydown', function (event) {
            if (event.key === 'Enter') {
                event.preventDefault();
                const first = list.querySelector('.select-search-option');
                if (first) {
                    first.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
                } else {
                    commitInput(select, input, list);
                }
            } else if (event.key === 'Escape') {
                input.value = selectedLabel(select);
                closeList(list);
            }
        });
        input.addEventListener('blur', function () {
            setTimeout(function () {
                commitInput(select, input, list);
            }, 120);
        });
        select.addEventListener('change', function () {
            input.value = selectedLabel(select);
        });
        window.addEventListener('scroll', function () {
            positionList(input, list);
        }, true);
        window.addEventListener('resize', function () {
            positionList(input, list);
        });
    }

    function enhanceAll(root) {
        (root || document).querySelectorAll('select.form-select, select.form-control').forEach(enhanceSelect);
    }

    document.addEventListener('DOMContentLoaded', function () {
        enhanceAll(document);
        document.addEventListener('click', function (event) {
            document.querySelectorAll('.select-search-list').forEach(function (list) {
                if (
                    !list.contains(event.target)
                    && !document.querySelector('.select-search:focus-within')
                ) {
                    closeList(list);
                }
            });
        });
        const observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                mutation.addedNodes.forEach(function (node) {
                    if (node.nodeType === 1) enhanceAll(node);
                });
            });
        });
        observer.observe(document.body, { childList: true, subtree: true });
    });

    window.enhanceSelectSearch = enhanceAll;
})();
