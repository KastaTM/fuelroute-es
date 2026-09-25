import { render, screen } from '@testing-library/react-native';

import App from '../App';

test('shows the bootstrap screen', async () => {
  await render(<App />);
  expect(screen.getByText('FuelRoute ES')).toBeTruthy();
  expect(screen.getByText('Base técnica lista')).toBeTruthy();
});
