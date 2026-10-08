import "@testing-library/jest-dom";

// jsdom has no layout engine; Layout scrolls to top on navigation.
window.scrollTo = () => {};
