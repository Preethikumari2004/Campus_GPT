import { useEffect, useId, useMemo, useState } from 'react'

/**
 * A small searchable select for choosing records loaded from the API.
 * Each option should be shaped like { value, label }.
 */
export default function SearchableSelect({
  label,
  value,
  options = [],
  onChange,
  placeholder = 'Type to search…',
  emptyMessage = 'No matching options',
  disabled = false,
  required = false,
}) {
  const generatedId = useId()
  const inputId = `search-select-${generatedId}`
  const listId = `${inputId}-options`
  const [query, setQuery] = useState('')
  const [isOpen, setIsOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)

  const selectedOption = options.find((option) => String(option.value) === String(value))
  const selectedLabel = selectedOption?.label || ''

  useEffect(() => {
    if (!isOpen) setQuery(selectedLabel)
  }, [isOpen, selectedLabel])

  const filteredOptions = useMemo(() => {
    const search = (isOpen ? query : '').trim().toLocaleLowerCase()
    if (!search) return options
    return options.filter((option) => option.label.toLocaleLowerCase().includes(search))
  }, [isOpen, options, query])

  function choose(option) {
    onChange(option.value)
    setQuery(option.label)
    setIsOpen(false)
    setActiveIndex(-1)
  }

  function handleKeyDown(event) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      if (!isOpen || activeIndex < 0) setActiveIndex(0)
      else setActiveIndex((index) => Math.min(index + 1, Math.max(filteredOptions.length - 1, 0)))
      setIsOpen(true)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      if (!isOpen || activeIndex < 0) setActiveIndex(Math.max(filteredOptions.length - 1, 0))
      else setActiveIndex((index) => Math.max(index - 1, 0))
      setIsOpen(true)
    } else if (event.key === 'Enter' && isOpen && filteredOptions[activeIndex]) {
      event.preventDefault()
      choose(filteredOptions[activeIndex])
    } else if (event.key === 'Escape') {
      setIsOpen(false)
      setActiveIndex(-1)
    }
  }

  return (
    <div className="searchable-select">
      <label htmlFor={inputId}>{label}</label>
      <div className="searchable-select-control">
        <input
          id={inputId}
          type="text"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={isOpen}
          aria-controls={listId}
          aria-activedescendant={isOpen && filteredOptions[activeIndex] ? `${listId}-${activeIndex}` : undefined}
          aria-required={required}
          autoComplete="off"
          disabled={disabled}
          value={isOpen ? query : selectedLabel}
          placeholder={placeholder}
          onFocus={() => {
            setQuery('')
            setActiveIndex(-1)
            setIsOpen(true)
          }}
          onChange={(event) => {
            setQuery(event.target.value)
            setActiveIndex(-1)
            setIsOpen(true)
          }}
          onKeyDown={handleKeyDown}
          onBlur={() => {
            setIsOpen(false)
            setQuery(selectedLabel)
          }}
        />
        <button
          className="searchable-select-toggle"
          type="button"
          aria-label={isOpen ? `Close ${label} options` : `Show ${label} options`}
          aria-expanded={isOpen}
          disabled={disabled}
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => {
            if (isOpen) {
              setIsOpen(false)
              setQuery(selectedLabel)
            } else {
              setQuery('')
              setActiveIndex(-1)
              setIsOpen(true)
            }
          }}
        >
          ▾
        </button>
        {isOpen && (
          <ul className="searchable-select-options" id={listId} role="listbox">
            {filteredOptions.length === 0 ? (
              <li className="searchable-select-empty" role="status">{emptyMessage}</li>
            ) : filteredOptions.map((option, index) => (
              <li
                id={`${listId}-${index}`}
                key={option.value}
                role="option"
                aria-selected={String(option.value) === String(value)}
                className={index === activeIndex ? 'active' : ''}
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => choose(option)}
              >
                {option.label}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
