export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  const { className = "", ...rest } = props;
  return (
    <select {...rest} className={"min-h-11 rounded border border-gray-300 bg-white px-3 py-2 text-base sm:min-h-0 sm:px-2 sm:py-1 sm:text-sm " + className} />
  );
}
