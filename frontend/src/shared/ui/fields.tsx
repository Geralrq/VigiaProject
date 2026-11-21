import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

interface FieldProps {
  label: string;
  hint?: string;
  error?: string | null;
}

function describedBy(...ids: (string | false | null | undefined)[]): string | undefined {
  const value = ids.filter(Boolean).join(" ");
  return value || undefined;
}

function Field({
  id,
  label,
  hint,
  error,
  children,
}: FieldProps & { id: string; children: ReactNode }) {
  return (
    <div className="form-field">
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && (
        <p id={`${id}-hint`} className="muted">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  );
}

export function TextField({
  label,
  hint,
  error,
  ...input
}: FieldProps & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <Field id={id} label={label} hint={hint} error={error}>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(hint && `${id}-hint`, error && `${id}-error`)}
        {...input}
      />
    </Field>
  );
}

export function TextAreaField({
  label,
  hint,
  error,
  ...input
}: FieldProps & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId();
  return (
    <Field id={id} label={label} hint={hint} error={error}>
      <textarea
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(hint && `${id}-hint`, error && `${id}-error`)}
        {...input}
      />
    </Field>
  );
}

export function SelectField({
  label,
  hint,
  error,
  children,
  ...input
}: FieldProps & SelectHTMLAttributes<HTMLSelectElement>) {
  const id = useId();
  return (
    <Field id={id} label={label} hint={hint} error={error}>
      <select
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(hint && `${id}-hint`, error && `${id}-error`)}
        {...input}
      >
        {children}
      </select>
    </Field>
  );
}

interface ChoiceOption<T extends string> {
  value: T;
  label: string;
  hint?: string;
}

/** Grupo de opciones excluyentes con objetivos táctiles grandes (radios nativos). */
export function ChoiceGroup<T extends string>({
  legend,
  name,
  value,
  options,
  onChange,
}: {
  legend: string;
  name: string;
  value: T;
  options: readonly ChoiceOption<T>[];
  onChange: (value: T) => void;
}) {
  return (
    <fieldset className="choice-group">
      <legend>{legend}</legend>
      {options.map((option) => (
        <label key={option.value} className="choice">
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={value === option.value}
            onChange={() => onChange(option.value)}
          />
          <span>
            {option.label}
            {option.hint && <span className="muted"> · {option.hint}</span>}
          </span>
        </label>
      ))}
    </fieldset>
  );
}
