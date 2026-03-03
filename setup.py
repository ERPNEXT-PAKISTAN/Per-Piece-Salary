from setuptools import find_packages, setup


setup(
    name="per_piece_payroll",
    version="0.0.1",
    description="Per Piece Payroll and Salary Management",
    author="TCPL",
    author_email="admin@tcpl.local",
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
)
