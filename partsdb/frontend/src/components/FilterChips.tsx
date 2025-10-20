import React from 'react';

type FilterOption = {
  value: string;
  label: string;
};

type FilterChipsProps = {
  label: string;
  options: FilterOption[];
  selectedValues: string[];
  onChange: (values: string[]) => void;
  className?: string;
};

const FilterChips: React.FC<FilterChipsProps> = ({
  label,
  options,
  selectedValues,
  onChange,
  className = '',
}) => {
  const toggleValue = (value: string) => {
    if (selectedValues.includes(value)) {
      onChange(selectedValues.filter((v) => v !== value));
    } else {
      onChange([...selectedValues, value]);
    }
  };

  return (
    <div className={`mb-4 ${className}`}>
      <div className="text-sm font-medium text-gray-700 mb-2">{label}</div>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const isSelected = selectedValues.includes(option.value);
          return (
            <button
              key={option.value}
              onClick={() => toggleValue(option.value)}
              className={`px-3 py-1 text-sm font-medium rounded-full transition-colors focus:outline-none ${
                isSelected
                  ? 'bg-blue-600 text-white hover:bg-blue-700'
                  : 'bg-gray-200 text-gray-800 hover:bg-gray-300'
              }`}
            >
              {option.label}
            </button>
          );
        })}
        {options.length === 0 && (
          <span className="text-sm text-gray-500">No filter options available</span>
        )}
      </div>
    </div>
  );
};

export default FilterChips;