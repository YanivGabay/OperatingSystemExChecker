# Project Title



## Table of Contents

- [Installation](#installation)
- [Usage](#usage)
- [Contributing](#contributing)
- [License](#license)

## Installation
Make sure you have docker desktop installed on your machine. If not, you can download it from [here](https://www.docker.com/products/docker-desktop).


## Usage

in order to test the gcc version that suppose to be accurate,
for gcc 8.5.0-22 we can run the test container, which the 
actual container will use the test one.

```bash
docker build -f Dockerfile.test -t gcc-8.5.0-test .
```

than you can just use docker compose

```bash
docker-compose up
```


## Contributing



## License

