export function Button(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { className = "", type = "button", ...rest } = props;
  return (
    <button
      type={type}
      {...rest}
      className={
        "rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white " +
        "disabled:opacity-50 hover:bg-blue-700 " +
        className
      }
    />
  );
}
