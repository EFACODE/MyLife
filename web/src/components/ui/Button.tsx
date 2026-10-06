export function Button(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { className = "", type = "button", ...rest } = props;
  return (
    <button
      type={type}
      {...rest}
      className={
        "min-h-11 rounded bg-blue-600 px-4 py-2 text-base font-medium text-white sm:min-h-0 sm:px-3 sm:py-1.5 sm:text-sm " +
        "disabled:opacity-50 hover:bg-blue-700 " +
        className
      }
    />
  );
}
