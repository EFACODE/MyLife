export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  const { className = "", ...rest } = props;
  return (
    <select {...rest} className={"rounded border border-gray-300 px-2 py-1 text-sm " + className} />
  );
}
