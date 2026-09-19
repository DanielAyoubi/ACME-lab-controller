class PID:
    def __init__(self, kp, ki, kd, output):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        # Start the integral at the current output so switching the loop on does not jump.
        self.integral = output
        self.last_measurement = None

    def update(self, setpoint, measurement, dt):
        error = setpoint - measurement
        self.integral += self.ki * error * dt
        derivative = 0.0
        if self.last_measurement is not None:
            # On the measurement, not the error, so a new target does not kick the output.
            derivative = -self.kd * (measurement - self.last_measurement) / dt
        self.last_measurement = measurement
        output = self.kp * error + self.integral + derivative
        clamped = min(100.0, max(0.0, output))
        # The integral keeps only what the clamp let through, so it cannot wind up at 0 or 100.
        self.integral += clamped - output
        return clamped
